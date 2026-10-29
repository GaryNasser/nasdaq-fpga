// tb_realfile_bp: real capture WITH backpressure on both sides.
//
// The real-file test streams with a free-running sink and an always-ready
// source - the easiest conditions. On hardware both sides stutter: the DMA
// inserts gaps between beats and the downstream parser applies backpressure.
// A 4096-byte-periodic bug hid behind clean conditions before, so this replays
// the same capture with:
//
//   * random gaps inserted before beats (source stalling), and
//   * random M_AXIS backpressure (sink stalling),
//
// and requires the same exact counts.
`timescale 1ns / 1ps

module tb_realfile_bp;

  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;

  reg  [4:0]  s_axi_awaddr = 0;
  reg         s_axi_awvalid = 0;
  wire        s_axi_awready;
  reg  [31:0] s_axi_wdata = 0;
  reg         s_axi_wvalid = 0;
  wire        s_axi_wready;
  wire [1:0]  s_axi_bresp;
  wire        s_axi_bvalid;
  reg         s_axi_bready = 1;
  reg  [4:0]  s_axi_araddr = 0;
  reg         s_axi_arvalid = 0;
  wire        s_axi_arready;
  wire [31:0] s_axi_rdata;
  wire [1:0]  s_axi_rresp;
  wire        s_axi_rvalid;
  reg         s_axi_rready = 1;

  reg  [63:0] s_axis_tdata = 0;
  reg  [7:0]  s_axis_tkeep = 8'hFF;
  reg         s_axis_tvalid = 0;
  wire        s_axis_tready;
  reg         s_axis_tlast = 0;

  wire [7:0]  m_axis_tdata;
  wire        m_axis_tvalid;
  reg         m_axis_tready = 1;

  mold64_reasm #(.SESSION(64'h4E41534441513031)) dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(s_axi_awaddr), .s_axi_awvalid(s_axi_awvalid),
    .s_axi_awready(s_axi_awready), .s_axi_wdata(s_axi_wdata),
    .s_axi_wstrb(4'hF), .s_axi_wvalid(s_axi_wvalid),
    .s_axi_wready(s_axi_wready), .s_axi_bresp(s_axi_bresp),
    .s_axi_bvalid(s_axi_bvalid), .s_axi_bready(s_axi_bready),
    .s_axi_araddr(s_axi_araddr), .s_axi_arvalid(s_axi_arvalid),
    .s_axi_arready(s_axi_arready), .s_axi_rdata(s_axi_rdata),
    .s_axi_rresp(s_axi_rresp), .s_axi_rvalid(s_axi_rvalid),
    .s_axi_rready(s_axi_rready),
    .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(s_axis_tkeep),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tlast(s_axis_tlast),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready)
  );

  parameter MAXB         = 1300000;
  parameter NPKT         = 850;
  parameter EXP_MESSAGES = 43428;
  parameter TOTAL_BYTES  = 1237116;

  reg [7:0] img [0:MAXB-1];
  integer   pkt_off [0:NPKT-1];
  integer   pkt_len [0:NPKT-1];

  integer k, p, off, cnt, m, mlen;
  integer seed;

  // Why is the READER stuck? Log the exact gating terms of the byte-consuming
  // states once the error count starts rising.
  integer rst;
  initial rst = 0;
  always @(posedge aclk) begin
    if (aresetn && dut.error_count != 0 && rst < 24) begin
      $display("RD st=%0d avail=%0d notempty=%b live=%b bytevld=%b rd=%0d cmt=%0d rdvalidd=%0d",
               dut.state, dut.fifo_available, dut.fifo_not_empty,
               dut.fifo_not_empty_live, dut.byte_valid_r, dut.pkt_rd_ptr,
               dut.bytes_committed, dut.rd_valid_d);
      rst = rst + 1;
    end
  end
  // Trace writer-side state across source gaps near the first failure.
  integer abs_wr;
  integer tstate;
  initial begin abs_wr = 0; tstate = 0; end
  always @(posedge aclk)
    if (aresetn && dut.s_wr_fire) abs_wr = abs_wr + dut.beat_bytes;

  always @(posedge aclk) begin
    if (aresetn && dut.error_count != 0 && tstate < 30) begin
      $display("ERR abs_wr=%0d wrptr=%0d hold_n=%0d cmt=%0d acc=%0d tailpend=%b rxpk=%0d",
               abs_wr, dut.pkt_wr_ptr, dut.hold_n, dut.bytes_committed,
               dut.bytes_accepted, dut.tail_pending, dut.rx_packets);
      tstate = tstate + 1;
    end
  end
  task axi_write(input [4:0] a, input [31:0] v);
    begin
      @(negedge aclk);
      s_axi_awaddr <= a; s_axi_awvalid <= 1;
      s_axi_wdata  <= v; s_axi_wvalid  <= 1;
      while (!(s_axi_awready && s_axi_wready)) @(negedge aclk);
      @(negedge aclk);
      s_axi_awvalid <= 0; s_axi_wvalid <= 0;
      while (!s_axi_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  // Random M_AXIS backpressure: hold the sink off for short bursts.
  initial begin
    seed = 32'h1234_5678;
    m_axis_tready = 1;
    forever begin
      @(negedge aclk);
      if (($random(seed) & 32'h7) == 0) begin
        m_axis_tready <= 0;
        repeat (($random(seed) & 32'hF) + 1) @(negedge aclk);
        m_axis_tready <= 1;
      end
    end
  end

  task send_pkt(input integer idx);
    integer q, len, base, done, gap;
    reg [63:0] wv;
    begin
      base = pkt_off[idx];
      len  = pkt_len[idx];
      q = 0;
      while (q < len) begin
        done = (len - q) < 8 ? (len - q) : 8;
        for (k = 0; k < 8; k = k + 1)
          wv[k*8 +: 8] = (k < done) ? img[base + q + k] : 8'h00;
        // Random source gaps, as a DMA would insert between beats.
        // A stalled source must hold TVALID LOW. Leaving it high would let
        // the receiver legitimately accept the same beat again, injecting
        // duplicates rather than a gap - which is what an earlier version of
        // this generator did, making the DUT look broken under invalid
        // stimulus.
        if (($random(seed) & 32'h7) == 0) begin
          gap = ($random(seed) & 32'h7) + 1;
          s_axis_tvalid <= 0;
          repeat (gap) @(negedge aclk);
        end
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
    for (p = 0; p < NPKT; p = p + 1) begin
      pkt_off[p] = off;
      cnt = {img[off+10], img[off+11]};
      m = off + 12;
      for (k = 0; k < cnt; k = k + 1) begin
        mlen = {img[m], img[m+1]};
        m = m + 2 + mlen;
      end
      pkt_len[p] = m - off;
      off = m;
    end
    $display("SCAN packets=%0d consumed=%0d expected=%0d", NPKT, off, TOTAL_BYTES);

    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);

    for (p = 0; p < NPKT; p = p + 1)
      send_pkt(p);

    @(negedge aclk);
    s_axis_tvalid <= 0;
    s_axis_tlast  <= 0;

    repeat (8000000) @(negedge aclk);

    $display("SIMTIME t=%0t", $time);
    $display("REALBP pkts=%0d rx_packets=%0d rx_messages=%0d gap=%0d err=%0d",
             NPKT, dut.rx_packets, dut.rx_messages, dut.gap_count,
             dut.error_count);

    if (dut.rx_packets == NPKT && dut.rx_messages == EXP_MESSAGES &&
        dut.gap_count == 0 && dut.error_count == 0)
      $display("REALBP-PASS");
    else
      $display("REALBP-FAIL");
    $finish;
  end

endmodule
