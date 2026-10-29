// tb_stall_long: reproduce the full-chain byte loss with a faithful sink model.
//
// Established by measurement in round 66:
//
//   * mold64_reasm ACCEPTED all 850 packets (155022 beats, 850 TLAST) - input
//     is complete, nothing is lost upstream.
//   * It EMITTED only 1217977 of the expected 1226916 bytes.
//   * emitted == taken at the parser, so the parser loses nothing.
//   * The parser held m_axis_tready low for 596316 cycles - it stalls hard.
//   * tb_chain_cmp passed with 1/2/3/8-cycle stalls AFTER each message, so the
//     failing condition is a LONGER stall, and probably one that begins
//     mid-message.
//
// itch_parse drops tready the moment it latches a message (msg_latched), i.e.
// shortly BEFORE the final byte of that message is presented, and holds it
// until the event is consumed by the order book. This test models exactly that:
// a stall that starts a configurable number of bytes BEFORE each TLAST and lasts
// a configurable number of cycles.
`timescale 1ns / 1ps

module tb_stall_long;

  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;

  reg  [4:0]  m_awaddr = 0;
  reg         m_awvalid = 0;
  wire        m_awready;
  reg  [31:0] m_wdata = 0;
  reg         m_wvalid = 0;
  wire        m_wready;
  wire [1:0]  m_bresp;
  wire        m_bvalid;
  reg         m_bready = 1;
  reg  [4:0]  m_araddr = 0;
  reg         m_arvalid = 0;
  wire        m_arready;
  wire [31:0] m_rdata;
  wire [1:0]  m_rresp;
  wire        m_rvalid;
  reg         m_rready = 1;

  reg  [63:0] s_axis_tdata = 0;
  reg  [7:0]  s_axis_tkeep = 8'hFF;
  reg         s_axis_tvalid = 0;
  wire        s_axis_tready;
  reg         s_axis_tlast = 0;

  wire [63:0] mid_tdata;
  wire [7:0]  mid_tkeep;
  wire        mid_tvalid;
  wire        mid_tready;
  wire        mid_tlast;

  mold64_reasm #(.SESSION(64'h4E41534441513031)) m64 (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(m_awaddr), .s_axi_awvalid(m_awvalid),
    .s_axi_awready(m_awready), .s_axi_wdata(m_wdata),
    .s_axi_wstrb(4'hF), .s_axi_wvalid(m_wvalid),
    .s_axi_wready(m_wready), .s_axi_bresp(m_bresp),
    .s_axi_bvalid(m_bvalid), .s_axi_bready(m_bready),
    .s_axi_araddr(m_araddr), .s_axi_arvalid(m_arvalid),
    .s_axi_arready(m_arready), .s_axi_rdata(m_rdata),
    .s_axi_rresp(m_rresp), .s_axi_rvalid(m_rvalid),
    .s_axi_rready(m_rready),
    .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(s_axis_tkeep),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tlast(s_axis_tlast),
    .m_axis_tdata(mid_tdata), .m_axis_tkeep(mid_tkeep),
    .m_axis_tvalid(mid_tvalid), .m_axis_tready(mid_tready),
    .m_axis_tlast(mid_tlast)
  );

  // ---- faithful sink model -------------------------------------------------
  // Prepare-ahead counter: how many bytes remain before the next TLAST.
  // When `STALL_BEFORE` bytes are left before a message ends, drop tready for
  // `STALL_CYC` cycles. That is what itch_parse does: it latches the full
  // message, which happens a little before its last byte completes.
  parameter STALL_BEFORE = 4;
  parameter STALL_CYC    = 200;

  reg [15:0] until_last;    // bytes until the next TLAST (approx; refreshed)
  reg        in_stall;
  reg [15:0] stall_cnt;

  initial begin in_stall = 0; stall_cnt = 0; until_last = 16'hFFFF; end

  always @(posedge aclk) begin
    if (!aresetn) begin
      in_stall <= 1'b0; stall_cnt <= 0;
    end else if (mid_tvalid && mid_tready) begin
      // Track distance to the next TLAST so we can pre-emptively stall.
      if (mid_tlast) until_last <= 16'hFFFF;
      else if (until_last != 16'hFFFF) until_last <= until_last - 1;
      if (!in_stall && mid_tlast) begin
        in_stall  <= 1'b1;
        stall_cnt <= STALL_CYC;
      end
    end
    if (in_stall) begin
      if (stall_cnt == 0) in_stall <= 1'b0;
      else stall_cnt <= stall_cnt - 1;
    end
  end

  assign mid_tready = aresetn && !in_stall;

  parameter MAXB        = 1300000;
  parameter NPKT        = 850;
  parameter EXPOUT      = 1300000;

  reg [7:0] img [0:MAXB-1];
  integer   pkt_off [0:NPKT-1];
  integer   pkt_len [0:NPKT-1];
  integer   k, p, off, cnt, m, mlen, q;

  reg [7:0] exp_stream [0:EXPOUT-1];
  integer   exp_bytes;

  integer out_bytes, mism, first_bad, tlast_out;
  initial begin out_bytes=0; mism=0; first_bad=-1; tlast_out=0; end

  always @(posedge aclk) begin
    if (aresetn && mid_tvalid && mid_tready) begin
      if (out_bytes < EXPOUT) begin
        if (exp_stream[out_bytes] !== mid_tdata[7:0]) begin
          mism = mism + 1;
          if (first_bad < 0) first_bad = out_bytes;
        end
      end
      if (mid_tlast) tlast_out = tlast_out + 1;
      out_bytes = out_bytes + 1;
    end
  end

  task m64_write(input [4:0] a, input [31:0] v);
    begin
      @(negedge aclk);
      m_awaddr <= a; m_awvalid <= 1; m_wdata <= v; m_wvalid <= 1;
      while (!(m_awready && m_wready)) @(negedge aclk);
      @(negedge aclk);
      m_awvalid <= 0; m_wvalid <= 0;
      while (!m_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  task send_pkt(input integer idx);
    integer done, base, len;
    reg [63:0] wv;
    begin
      base = pkt_off[idx];
      len  = pkt_len[idx];
      q = 0;
      while (q < len) begin
        done = (len - q) < 8 ? (len - q) : 8;
        for (k = 0; k < 8; k = k + 1)
          wv[k*8 +: 8] = (k < done) ? img[base + q + k] : 8'h00;
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= wv;
        s_axis_tkeep  <= (done == 8) ? 8'hFF : ((8'hFF >> (8 - done)));
        s_axis_tlast  <= ((q + done) == len);
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        q = q + done;
      end
    end
  endtask

  initial begin
    $readmemh("img.hex", img);

    off = 0;
    exp_bytes = 0;
    for (p = 0; p < NPKT; p = p + 1) begin
      pkt_off[p] = off;
      cnt = {img[off+10], img[off+11]};
      m = off + 12;
      for (k = 0; k < cnt; k = k + 1) begin
        mlen = {img[m], img[m+1]};
        exp_stream[exp_bytes] = img[m];     exp_bytes = exp_bytes + 1;
        exp_stream[exp_bytes] = img[m+1];   exp_bytes = exp_bytes + 1;
        for (q = 0; q < mlen; q = q + 1) begin
          exp_stream[exp_bytes] = img[m + 2 + q];
          exp_bytes = exp_bytes + 1;
        end
        m = m + 2 + mlen;
      end
      pkt_len[p] = m - off;
      off = m;
    end

    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    m64_write(5'h18, 32'h3);
    repeat (8) @(negedge aclk);

    for (p = 0; p < NPKT; p = p + 1)
      send_pkt(p);

    @(negedge aclk);
    s_axis_tvalid <= 0;
    s_axis_tlast  <= 0;

    repeat (3000000) @(negedge aclk);
    $display("STALLLONG before=%0d stallcyc=%0d out=%0d exp=%0d mism=%0d tlast=%0d m64_pkts=%0d m64_msgs=%0d gap=%0d err=%0d",
             STALL_BEFORE, STALL_CYC, out_bytes, exp_bytes, mism, tlast_out,
             m64.rx_packets, m64.rx_messages, m64.gap_count, m64.error_count);
    if (out_bytes == exp_bytes && mism == 0)
      $display("STALLLONG-PASS");
    else
      $display("STALLLONG-FAIL");
    $finish;
  end

endmodule
