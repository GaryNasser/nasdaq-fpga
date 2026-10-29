// tb_chain_cmp: find exactly WHICH bytes are lost between the modules.
//
// tb_fullchain showed the chain drops 19139 of 1237116 bytes when the real
// parser applies backpressure. Reasoning about the FSM has not produced a
// verified cause, so this measures instead: it records every byte the
// reassembler puts on m_axis and compares that stream against the stream
// tb_realfile proves it should produce (2-byte length prefix + body, per
// message), reporting the first divergence and its context.
`timescale 1ns / 1ps

module tb_chain_cmp;

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

  // Sink that emulates itch_parse's readiness pattern closely enough to expose
  // the inter-module stall, without dragging in the whole parser.
  //   tready low for N cycles every time a "message" completes.
  parameter MSG_GAP_CYC = 8;
  reg [15:0] gap_cnt;
  reg        in_gap;
  initial begin gap_cnt = 0; in_gap = 0; end

  always @(posedge aclk) begin
    if (!aresetn) begin in_gap <= 1'b0; gap_cnt <= 0; end
    else if (in_gap) begin
      if (gap_cnt == 0) in_gap <= 1'b0;
      else gap_cnt <= gap_cnt - 1;
    end else if (mid_tvalid && mid_tready && mid_tlast) begin
      in_gap  <= 1'b1;
      gap_cnt <= MSG_GAP_CYC;
    end
  end
  assign mid_tready = aresetn && !in_gap;

  parameter MAXB        = 1300000;
  parameter NPKT        = 850;
  parameter TOTAL_BYTES = 1237116;
  parameter EXPOUT      = 1300000;

  reg [7:0] img [0:MAXB-1];
  integer   pkt_off [0:NPKT-1];
  integer   pkt_len [0:NPKT-1];
  integer   k, p, off, cnt, m, mlen, q;

  // Expected output stream (length prefix + body per message).
  reg [7:0] exp_stream [0:EXPOUT-1];
  integer   exp_bytes;

  // Observed stream.
  integer out_bytes, mism, first_bad;
  initial begin out_bytes = 0; mism = 0; first_bad = -1; end

  always @(posedge aclk) begin
    if (aresetn && mid_tvalid && mid_tready) begin
      if (out_bytes < EXPOUT) begin
        if (exp_stream[out_bytes] !== mid_tdata[7:0]) begin
          mism = mism + 1;
          if (first_bad < 0) begin
            first_bad = out_bytes;
            $display("  FIRST-BAD at out byte %0d got=%02h want=%02h",
                     out_bytes, mid_tdata[7:0], exp_stream[out_bytes]);
          end
        end
      end
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
    $display("SCAN packets=%0d consumed=%0d expout=%0d", NPKT, off, exp_bytes);

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

    repeat (2000000) @(negedge aclk);
    $display("CMP out_bytes=%0d exp_bytes=%0d mismatches=%0d first_bad=%0d",
             out_bytes, exp_bytes, mism, first_bad);
    if (out_bytes == exp_bytes && mism == 0 && first_bad < 0)
      $display("CMP-PASS");
    else
      $display("CMP-FAIL");
    $finish;
  end

endmodule
