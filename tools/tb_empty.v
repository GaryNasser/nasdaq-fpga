// tb_empty: what does the reassembler do when it receives NOTHING?
//
// A board session can enable the pipeline and start a DMA transfer that delivers zero beats - a failed
// descriptor, a zero-length buffer, a driver bug. Nothing in the 30-suite set drives that case: every bench
// feeds at least one packet.
//
// What must hold:
//
//     no counters move          rx_packets, rx_messages, gap_count, error_count all stay 0
//     no claim happens          the FSM never enters a session state
//     nothing is emitted        m_axis_tvalid stays low
//     the module stays ready    s_axis_tready high, so a later transfer would be accepted
//
// A design that latches a false error on an empty transfer would report a failure on a board whose driver
// sent nothing - and the board_recover path treats any FAIL line as a failure.
`timescale 1ns / 1ps

module tb_empty;

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

  reg [7:0] pkt [0:31];
  reg [63:0] beat;
  integer errors = 0, b, j;
  integer i;
  integer emitted = 0;

  always @(posedge aclk)
    if (aresetn && m_tvalid && m_tready) emitted = emitted + 1;

  initial begin
    aresetn = 0;
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);

    // Enable the pipeline, exactly as the driver does.
    @(negedge aclk);
    awaddr = 5'h18; wdata = 32'h1; awvalid = 1; wvalid = 1;
    @(posedge aclk);
    for (i = 0; i < 50 && !(awready && wready); i = i + 1) @(posedge aclk);
    @(negedge aclk);
    awvalid = 0; wvalid = 0;
    repeat (3) @(negedge aclk);

    if (dut.enable !== 1'b1) begin
      $display("EMPTY-FAIL: enable never asserted - the DUT was never turned on");
      errors = errors + 1;
    end

    // Deliver NOTHING for a long while - the empty transfer.
    repeat (500) @(negedge aclk);

    $display("EMPTY counters pkts=%0d msgs=%0d gap=%0d err=%0d emitted=%0d tready=%b",
             dut.rx_packets, dut.rx_messages, dut.gap_count, dut.error_count,
             emitted, s_tready);

    if (dut.rx_packets !== 16'd0) begin
      $display("EMPTY-FAIL: rx_packets=%0d on an empty transfer", dut.rx_packets);
      errors = errors + 1;
    end
    if (dut.rx_messages !== 16'd0) begin
      $display("EMPTY-FAIL: rx_messages=%0d on an empty transfer", dut.rx_messages);
      errors = errors + 1;
    end
    if (dut.gap_count !== 16'd0) begin
      $display("EMPTY-FAIL: gap_count=%0d on an empty transfer", dut.gap_count);
      errors = errors + 1;
    end
    if (dut.error_count !== 16'd0) begin
      $display("EMPTY-FAIL: error_count=%0d on an empty transfer", dut.error_count);
      errors = errors + 1;
    end
    if (emitted != 0) begin
      $display("EMPTY-FAIL: %0d beats emitted from no input", emitted);
      errors = errors + 1;
    end
    if (s_tready !== 1'b1) begin
      $display("EMPTY-FAIL: tready is low after an empty transfer - a later transfer would be refused");
      errors = errors + 1;
    end

    // And the module must still work afterwards: send one minimal well-formed packet.
    //
    // Built as BYTES and packed into beats, so no 64-bit constant can be byte-transposed. The session id is the
    // one the capture uses, in wire order: 4E 41 53 44 41 51 30 31.
    pkt[0]=8'h4E; pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
    pkt[4]=8'h41; pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;   // session
    pkt[8]=8'h00; pkt[9]=8'h00;                               // sequence = 0
    pkt[10]=8'h00; pkt[11]=8'h01;                             // count = 1
    pkt[12]=8'h00; pkt[13]=8'h04;                             // length = 4
    pkt[14]=8'h41; pkt[15]=8'h42; pkt[16]=8'h43; pkt[17]=8'h44; // payload "ABCD"

    for (b = 0; b < 18; b = b + 8) begin
      beat = 64'd0;
      for (j = 0; j < 8; j = j + 1)
        if ((b + j) < 18) beat[j*8 +: 8] = pkt[b + j];
      @(negedge aclk);
      s_tdata  = beat;
      s_tkeep  = ((18 - b) >= 8) ? 8'hFF : (8'hFF >> (8 - (18 - b)));
      s_tvalid = 1;
      s_tlast  = ((b + 8) >= 18);
      @(posedge aclk);
      while (!s_tready) @(posedge aclk);
    end

    @(negedge aclk);
    s_tvalid = 0; s_tlast = 0;
    repeat (400) @(negedge aclk);

    $display("EMPTY after a minimal packet: pkts=%0d msgs=%0d err=%0d",
             dut.rx_packets, dut.rx_messages, dut.error_count);
    if (dut.rx_packets < 16'd1) begin
      $display("EMPTY-FAIL: the module did not recover - rx_packets still 0 after a valid transfer");
      errors = errors + 1;
    end

    if (errors == 0) $display("EMPTY-PASS");
    else begin
      $display("EMPTY-FAIL (%0d)", errors);
      $display("EMPTY-TB-DONE");
    end
    $finish;
  end

endmodule
