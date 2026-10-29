// tb_emit_bytes: with the SAME stimulus as tb_realfile, verify the EMITTED bytes are the right ones.
//
// Round 170's attempt (tb_stream_bytes) produced a dramatic result and was then found to have a stimulus
// bug: `tkeep = 8'hFF` on every beat, declaring 8 bytes where the stream held fewer. Withdrawn.
//
// This one copies tb_realfile's stimulus verbatim - per-packet TLAST, tkeep masked to the remaining bytes
// at each packet's end - and adds what tb_realfile lacks: it collects every M_AXIS byte and compares the
// stream against the capture's messages.
//
// What the design re-emits, per MoldUDP64 message, is its 2-byte Length field followed by the payload.
// The comparison is a count plus a running checksum, since 1.2 MB of expected bytes cannot be held in a
// testbench practically.
`timescale 1ns / 1ps

module tb_emit_bytes;

  parameter MAXB = 1300000;
  parameter NPKT = 850;
  parameter TOTAL_BYTES = 1237116;

  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;

  reg  [4:0]  awaddr = 0;
  reg         awvalid = 0;
  wire        awready;
  reg  [31:0] wdata = 0;
  reg         wvalid = 0;
  wire        wready;
  wire [1:0]  bresp;
  wire        bvalid;
  reg         bready = 1;
  reg  [4:0]  araddr = 0;
  reg         arvalid = 0;
  wire        arready;
  wire [31:0] rdata;
  wire [1:0]  rresp;
  wire        rvalid;
  reg         rready = 1;

  reg  [63:0] s_axis_tdata = 0;
  reg  [7:0]  s_axis_tkeep = 8'hFF;
  reg         s_axis_tvalid = 0;
  reg         s_axis_tlast = 0;
  wire        s_axis_tready;

  wire [63:0] m_axis_tdata;
  wire [7:0]  m_axis_tkeep;
  wire        m_axis_tvalid;
  reg         m_axis_tready = 1;

  mold64_reasm #(.SESSION(64'h4E41534441513031)) dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid),
    .s_axi_awready(awready), .s_axi_wdata(wdata), .s_axi_wstrb(5'h1F),
    .s_axi_wvalid(wvalid), .s_axi_wready(wready), .s_axi_bresp(bresp),
    .s_axi_bvalid(bvalid), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid),
    .s_axi_arready(arready), .s_axi_rdata(rdata), .s_axi_rresp(rresp),
    .s_axi_rvalid(rvalid), .s_axi_rready(rready),
    .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(s_axis_tkeep),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tlast(s_axis_tlast),
    .m_axis_tdata(m_axis_tdata), .m_axis_tkeep(m_axis_tkeep),
    .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready)
  );

  reg [7:0] img [0:MAXB-1];
  integer   pkt_off [0:NPKT-1];
  integer   pkt_len [0:NPKT-1];

  integer i, k, p, cnt, off, mlen, nbytes, done, q;
  integer img_len;

  // ---- emitted stream ----------------------------------------------------------------
  reg [31:0] emit_sum = 0;
  integer    emit_cnt = 0;

  always @(posedge aclk) begin
    if (aresetn && m_axis_tvalid && m_axis_tready) begin
      emit_sum <= (emit_sum * 31) + {24'd0, m_axis_tdata[7:0]};
      emit_cnt <= emit_cnt + 1;
    end
  end

  // ---- expected stream, computed from the capture ------------------------------------
  reg [31:0] exp_sum = 0;
  integer    exp_cnt = 0;
  integer    exp_msgs = 0;
  integer    ln, j;

  task send_pkt(input integer idx);
    integer qq, len, base, dn;
    reg [63:0] wv;
    begin
      base = pkt_off[idx];
      len  = pkt_len[idx];
      qq = 0;
      while (qq < len) begin
        dn = ((len - qq) < 8) ? (len - qq) : 8;
        for (k = 0; k < 8; k = k + 1)
          wv[k*8 +: 8] = (k < dn) ? img[base + qq + k] : 8'h00;
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= wv;
        s_axis_tkeep  <= (dn == 8) ? 8'hFF : ((8'hFF >> (8 - dn)));
        s_axis_tlast  <= ((qq + dn) == len);
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        qq = qq + dn;
      end
    end
  endtask

  initial begin
    $readmemh("img.hex", img);
    img_len = TOTAL_BYTES;

    // Packet boundaries.
    p = 0;
    for (i = 0; i < NPKT; i = i + 1) begin
      pkt_off[i] = p;
      cnt = {img[p+10], img[p+11]};
      p = p + 12;
      for (k = 0; k < cnt; k = k + 1) begin
        ln = {img[p], img[p+1]};
        p = p + 2 + ln;
      end
      pkt_len[i] = p - pkt_off[i];
    end
    $display("EMIT captured %0d packets, %0d bytes", NPKT, p);

    // Expected output: per message, the 2-byte Length then the payload.
    for (i = 0; i < NPKT; i = i + 1) begin
      off = pkt_off[i];
      cnt = {img[off+10], img[off+11]};
      off = off + 12;
      for (k = 0; k < cnt; k = k + 1) begin
        ln = {img[off], img[off+1]};
        exp_sum = (exp_sum * 31) + ln[15:8];
        exp_sum = (exp_sum * 31) + ln[7:0];
        exp_cnt = exp_cnt + 2;
        for (j = 0; j < ln; j = j + 1) begin
          exp_sum = (exp_sum * 31) + img[off + 2 + j];
          exp_cnt = exp_cnt + 1;
        end
        off = off + 2 + ln;
        exp_msgs = exp_msgs + 1;
      end
    end
    $display("EMIT expected %0d messages, %0d bytes, sum %08h",
             exp_msgs, exp_cnt, exp_sum);

    // Drive, same as tb_realfile.
    aresetn = 0;
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);

    @(negedge aclk);
    awaddr = 5'h18; wdata = 32'h1; awvalid = 1; wvalid = 1;
    @(posedge aclk);
    for (i = 0; i < 50 && !(awready && wready); i = i + 1) @(posedge aclk);
    @(negedge aclk);
    awvalid = 0; wvalid = 0;
    repeat (3) @(negedge aclk);

    for (i = 0; i < NPKT; i = i + 1)
      send_pkt(i);

    @(negedge aclk);
    s_axis_tvalid = 0;
    s_axis_tlast  = 0;

    repeat (4000) @(negedge aclk);

    $display("EMIT emitted  %0d bytes, sum %08h", emit_cnt, emit_sum);
    $display("EMIT counters pkts=%0d msgs=%0d gap=%0d err=%0d",
             dut.rx_packets, dut.rx_messages, dut.gap_count, dut.error_count);

    if (emit_cnt != exp_cnt)
      $display("EMIT-FAIL-COUNT: emitted %0d of %0d", emit_cnt, exp_cnt);
    else if (emit_sum !== exp_sum)
      $display("EMIT-FAIL-CHECKSUM: %08h vs %08h", emit_sum, exp_sum);
    else
      $display("EMIT-PASS: every emitted byte matches the capture");

    $finish;
  end

endmodule
