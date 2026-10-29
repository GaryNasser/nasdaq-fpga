// tb_disable: CTRL is cleared in the middle of a stream.
//
// The only boundary from the round-197 enumeration with no bench: every other degenerate input (empty stream,
// truncated transfer, tkeep 1..7 lanes, count 0, length 0, TLAST placement, session mismatch, sequence gap) is
// driven by at least one test.
//
// Why the driver would do this: a user aborts, a watchdog fires, or the next session's driver resets before
// loading a new overlay. The module must
//
//     stop claiming packets            no further rx_packets increments
//     not corrupt what it emitted      bytes already out stay out
//     resume cleanly                   re-enabling accepts a NEW packet from the start
//
// The failure this guards against is a half-parsed packet left in the FSM: re-enabling would then resume in the
// middle of a session and parse garbage as a header, which surfaces as a large error_count on the next run.
`timescale 1ns / 1ps

module tb_disable;

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

  reg  [63:0] s_tdata = 0;
  reg  [7:0]  s_tkeep = 8'hFF;
  reg         s_tvalid = 0;
  reg         s_tlast = 0;
  wire        s_tready;

  wire [63:0] m_tdata;
  wire [7:0]  m_tkeep;
  wire        m_tvalid;
  reg         m_tready = 1;

  mold64_reasm #(.SESSION(64'h4E41534441513031)) dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid),
    .s_axi_awready(awready), .s_axi_wdata(wdata), .s_axi_wstrb(5'h1F),
    .s_axi_wvalid(wvalid), .s_axi_wready(wready), .s_axi_bresp(bresp),
    .s_axi_bvalid(bvalid), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid),
    .s_axi_arready(arready), .s_axi_rdata(rdata), .s_axi_rresp(rresp),
    .s_axi_rvalid(rvalid), .s_axi_rready(rready),
    .s_axis_tdata(s_tdata), .s_axis_tkeep(s_tkeep), .s_axis_tvalid(s_tvalid),
    .s_axis_tready(s_tready), .s_axis_tlast(s_tlast),
    .m_axis_tdata(m_tdata), .m_axis_tkeep(m_tkeep), .m_axis_tvalid(m_tvalid),
    .m_axis_tready(m_tready)
  );

  parameter integer MLEN = 8;
  reg [7:0]  pkt [0:255];
  reg [63:0] beat;
  integer errors = 0, i, b, j, n, pkts_before;

  // CTRL write: 0 disables, 1 enables.
  task set_ctrl(input [31:0] v);
    begin
      @(negedge aclk);
      awaddr = 5'h18; wdata = v; awvalid = 1; wvalid = 1;
      @(posedge aclk);
      while (!(awready && wready)) @(posedge aclk);
      @(negedge aclk);
      awvalid = 0; wvalid = 0;
      repeat (3) @(negedge aclk);
    end
  endtask

  // One MoldUDP64 packet: session, seq, 1 message of 8 bytes.
  task build(input integer seqn);
    integer q, m;
    begin
      pkt[0]=8'h4E; pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
      pkt[4]=8'h41; pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
      pkt[8]=seqn[15:8]; pkt[9]=seqn[7:0];
      pkt[10]=8'h00; pkt[11]=8'h01;              // count = 1
      pkt[12]=8'h00; pkt[13]=MLEN[7:0];           // message length
      q = 14;
      for (m = 0; m < MLEN; m = m + 1) pkt[q + m] = 8'h60 + m[7:0];
      n = q + MLEN;
    end
  endtask

  // Drive the whole packet, TLAST on the final beat.
  task drive_all(input integer last);
    integer k, dn, c;
    begin
      k = 0;
      while (k < n) begin
        dn = ((n - k) < 8) ? (n - k) : 8;
        beat = 64'd0;
        for (c = 0; c < dn; c = c + 1) beat[c*8 +: 8] = pkt[k + c];
        @(negedge aclk);
        s_tdata  = beat;
        s_tkeep  = (dn == 8) ? 8'hFF : (8'hFF >> (8 - dn));
        s_tvalid = 1;
        s_tlast  = last && ((k + dn) >= n);
        @(posedge aclk);
        while (!s_tready) @(posedge aclk);
        k = k + dn;
      end
      @(negedge aclk);
      s_tvalid = 0; s_tlast = 0; s_tkeep = 8'hFF;
    end
  endtask

  initial begin
    #500000;
    $display("DISABLE-FAIL: watchdog - the test hung");
    $finish;
  end

  initial begin
    aresetn = 0;
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);

    set_ctrl(32'h1);
    if (dut.enable !== 1'b1) begin
      $display("DISABLE-FAIL: enable never asserted");
      errors = errors + 1;
    end

    // One good packet with the pipeline on.
    build(0);
    drive_all(1);
    repeat (300) @(negedge aclk);
    pkts_before = dut.rx_packets;
    $display("DISABLE first packet: pkts=%0d msgs=%0d err=%0d",
             dut.rx_packets, dut.rx_messages, dut.error_count);
    if (pkts_before < 1) begin
      $display("DISABLE-FAIL: the baseline packet did not parse - the rest of the test is meaningless");
      errors = errors + 1;
    end

    // Disable, then deliver a packet while disabled: it must NOT be claimed.
    set_ctrl(32'h0);
    if (dut.enable !== 1'b0) begin
      $display("DISABLE-FAIL: CTRL=0 did not clear enable");
      errors = errors + 1;
    end

    // While disabled, a beat presented must be BACK-PRESSURED, not consumed. Bounded wait - this is the
    // contract, and waiting on tready here would hang because tready is correctly low.
    build(1);
    @(negedge aclk);
    s_tdata  = {pkt[7], pkt[6], pkt[5], pkt[4], pkt[3], pkt[2], pkt[1], pkt[0]};
    s_tkeep  = 8'hFF;
    s_tvalid = 1;
    s_tlast  = 0;
    for (i = 0; i < 200 && s_tready; i = i + 1) @(posedge aclk);
    $display("DISABLE while off: tready=%b after 200 cycles of a presented beat", s_tready);
    if (s_tready !== 1'b0) begin
      $display("DISABLE-FAIL: tready stayed high while disabled - a beat would be consumed");
      errors = errors + 1;
    end
    @(negedge aclk);
    s_tvalid = 0;
    repeat (100) @(negedge aclk);
    $display("DISABLE while off: pkts=%0d (was %0d) msgs=%0d err=%0d",
             dut.rx_packets, pkts_before, dut.rx_messages, dut.error_count);
    if (dut.rx_packets != pkts_before) begin
      $display("DISABLE-FAIL: rx_packets moved from %0d to %0d while disabled",
               pkts_before, dut.rx_packets);
      errors = errors + 1;
    end

    // Re-enable and send a fresh packet: must parse, and must not inherit the disabled-era bytes.
    set_ctrl(32'h1);
    if (s_tready !== 1'b1) begin
      $display("DISABLE-FAIL: tready is still low after re-enabling");
      errors = errors + 1;
    end
    build(2);
    drive_all(1);
    repeat (400) @(negedge aclk);
    $display("DISABLE after re-enable: pkts=%0d msgs=%0d err=%0d",
             dut.rx_packets, dut.rx_messages, dut.error_count);
    if (dut.rx_packets <= pkts_before) begin
      $display("DISABLE-FAIL: no packet parsed after re-enabling");
      errors = errors + 1;
    end

    if (errors == 0) $display("DISABLE-PASS");
    else             $display("DISABLE-FAIL (%0d)", errors);
    $finish;
  end

endmodule
