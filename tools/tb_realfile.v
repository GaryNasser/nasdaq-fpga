// tb_realfile: drive the reassembler with the REAL capture file.
//
// Every streaming test so far used synthetic packets. The hardware replay feeds
// itch_loc6836.mold64 - 850 packets carrying 43428 messages, real ITCH traffic
// with the mix of message types, sizes and packet boundaries that only appears
// in a capture. If that file parses correctly in simulation, a failure on the
// board is a hardware or driver problem rather than a logic one.
//
// The file image is loaded with $readmemh (see tools/make_realfile.py) and
// streamed packet by packet, back to back, with TKEEP and TLAST derived from
// each packet's actual length exactly as the DMA would present them.
`timescale 1ns / 1ps

module tb_realfile;

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

  integer i, k, b, p, n, off, cnt, m, mlen;
  reg [63:0] w;

  // Record the first packet index at which a parse error appears, and the
  // sequence number the parser had reached - the decisive datum.
  integer last_err;
  integer first_err_pkt;
  integer first_err_seq;
  integer gap_seq_seen;
  initial begin last_err = 0; first_err_pkt = -1; first_err_seq = -1; gap_seq_seen = -1; end
  always @(posedge aclk) begin
    if (dut.error_count != last_err) begin
      if (last_err == 0 && first_err_pkt < 0 && p < NPKT) begin
        first_err_pkt = p;
        first_err_seq = dut.rx_seq;
        $display("FIRSTERR after sending pkt index %0d, rx_seq=%0d expect=%0d rd=%0d acc=%0d wrote=%0d",
                 p, dut.rx_seq, dut.expect_seq, dut.pkt_rd_ptr, dut.bytes_accepted,
                 pkt_off[p < NPKT ? p : NPKT-1]);
      end
      last_err = dut.error_count;
    end
    if (gap_seq_seen < 0 && dut.gap_count != 0) begin
      gap_seq_seen = p;
      $display("FIRSTGAP at pkt index %0d rx_seq=%0d expect=%0d", p, dut.rx_seq, dut.expect_seq);
    end
  end
  // Classify the first error: which of the three increment sites fired?
  integer e_sess, e_trunc, e_under;
  reg prev_sess_err;
  initial begin e_sess = 0; e_trunc = 0; e_under = 0; prev_sess_err = 0; end
  always @(posedge aclk) begin
    if (dut.session_mismatch && dut.byte_valid_r && dut.fifo_not_empty_live &&
        (dut.state >= 5'd1 && dut.state <= 5'd8)) begin
      if (e_sess == 0) $display("ERRSITE session_mismatch at p=%0d rd=%0d byte=%h want=4e", p, dut.pkt_rd_ptr, dut.cur_byte);
      e_sess = e_sess + 1;
    end
    if (dut.state == 5'd13 && dut.byte_valid_r && dut.fifo_not_empty_live &&
        !dut.last_msg_done && (dut.pkt_rd_ptr == dut.bytes_committed)) begin
      if (e_trunc == 0) $display("ERRSITE truncated at p=%0d rd=%0d", p, dut.pkt_rd_ptr);
      e_trunc = e_trunc + 1;
    end
    if ((dut.state == 5'd15) && dut.bytes_rem_gt0_r && !dut.fifo_not_empty_live) begin
      if (e_under == 0) $display("ERRSITE underflow at p=%0d rd=%0d", p, dut.pkt_rd_ptr);
      e_under = e_under + 1;
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

  // Send one packet: bytes [pkt_off[p], pkt_off[p]+pkt_len[p]), back to back.
  task send_pkt(input integer idx);
    integer q, len, base, done;
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

    // Derive packet boundaries from the MoldUDP64 framing.
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

    repeat (4000000) @(negedge aclk);

    $display("ERRSITES sess=%0d trunc=%0d under=%0d", e_sess, e_trunc, e_under);
    $display("REALFILE pkts=%0d rx_packets=%0d rx_messages=%0d gap=%0d err=%0d",
             NPKT, dut.rx_packets, dut.rx_messages, dut.gap_count,
             dut.error_count);

    if (dut.rx_packets == NPKT && dut.rx_messages == EXP_MESSAGES &&
        dut.gap_count == 0)
      $display("REALFILE-PASS");
    else
      $display("REALFILE-FAIL");
    $finish;
  end

endmodule
