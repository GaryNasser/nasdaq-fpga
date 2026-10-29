// tb_ram_trace: with a zeroed RAM, follow the FSM packet by packet.
//
// The zeroed-RAM bench keeps 0 of 4 packets with err=49 - so it consumed about one packet's worth of
// rescan and stopped. The board keeps 849 of 850. The shapes differ, so this traces WHERE the zeroed
// case goes after the first failure.
//
// Printing on each state transition into and out of a rescan, with the pointer and error count, shows
// whether the FSM rewinds to ST_IDLE (which would let packet 2 start) or stays in a session state.
`timescale 1ns / 1ps

module tb_ram_trace;

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
  wire        m_tready;

  assign m_tready = 1'b1;

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

  reg [7:0] stream [0:255];
  integer   i;
  integer   k;
  integer   npkts;
  integer   plen;
  integer   last_state = -1;

  initial begin
    for (i = 0; i < 512; i = i + 1)
      dut.pkt_ram[i] = 64'd0;

    npkts = 3;
    plen  = 50;
    for (k = 0; k < npkts; k = k + 1) begin
      stream[k*plen + 0]=8'h4E; stream[k*plen + 1]=8'h41;
      stream[k*plen + 2]=8'h53; stream[k*plen + 3]=8'h44;
      stream[k*plen + 4]=8'h41; stream[k*plen + 5]=8'h51;
      stream[k*plen + 6]=8'h30; stream[k*plen + 7]=8'h31;
      stream[k*plen + 8]=8'h00; stream[k*plen + 9]=k[7:0];
      stream[k*plen +10]=8'h00; stream[k*plen +11]=8'h01;
      stream[k*plen +12]=8'h00; stream[k*plen +13]=8'h24;
      for (i = 0; i < 36; i = i + 1)
        stream[k*plen + 14 + i] = (i == 0) ? 8'h41 : (8'h10 + i[7:0]);
    end
  end

  // Trace every state change.
  always @(posedge aclk) begin
    if (aresetn && dut.state !== last_state) begin
      $display("TRACE t=%0t st=%0d rd=%0d avail=%0d err=%0d pkts=%0d",
               $time, dut.state, dut.pkt_rd_ptr, dut.fifo_available,
               dut.error_count, dut.rx_packets);
      last_state <= dut.state;
    end
  end

  initial begin
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

    k = 0;
    while (k < npkts * plen) begin
      @(negedge aclk);
      s_tdata  = {56'd0, stream[k]};
      s_tkeep  = 8'h01;
      s_tvalid = 1;
      s_tlast  = ((k + 1) >= npkts * plen);
      @(posedge aclk);
      i = 0;
      while (!s_tready && i < 500) begin
        @(posedge aclk);
        i = i + 1;
      end
      k = k + 1;
    end
    @(negedge aclk);
    s_tvalid = 0;
    s_tlast  = 0;

    repeat (600) @(negedge aclk);

    $display("TRACE-END pkts=%0d of %0d err=%0d gap=%0d rd=%0d",
             dut.rx_packets, npkts, dut.error_count, dut.gap_count, dut.pkt_rd_ptr);
    $finish;
  end

endmodule
