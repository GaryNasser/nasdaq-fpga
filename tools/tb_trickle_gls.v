// tb_trickle_gls: drive the GATE-LEVEL mold64_reasm and read its counters through AXI-Lite.
//
// The gate-level netlist has no hierarchical signals - `dut.rx_packets` and `dut.state` do not exist.
// Counters must be read from the register map, which is also how the board reports them.
//
// Register map (mold64_reasm):
//     0x00 RX_PACKETS_LO   0x04 RX_PACKETS_HI
//     0x08 RX_MESSAGES_LO  0x0C RX_MESSAGES_HI
//     0x10 GAP_COUNT       0x14 ERROR_COUNT
//     0x18 CTRL
//
// The stimulus is tb_trickle's: one byte per beat, FSM enabled first. Against the deployed netlist
// it answers the one question behavioural simulation cannot.
`timescale 1ns / 1ps

module tb_trickle_gls;

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

  mold64_reasm dut (
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

  reg [7:0] pkt [0:63];
  integer   i;
  integer   k;
  integer   nbytes;
  integer   rd;

  task axi_write;
    input [4:0]  addr;
    input [31:0] data;
    begin
      @(negedge aclk);
      awaddr = addr; wdata = data; awvalid = 1; wvalid = 1;
      @(posedge aclk);
      for (i = 0; i < 50 && !(awready && wready); i = i + 1) @(posedge aclk);
      @(negedge aclk);
      awvalid = 0; wvalid = 0;
    end
  endtask

  task axi_read;
    input  [4:0]  addr;
    begin
      @(negedge aclk);
      araddr = addr; arvalid = 1;
      @(posedge aclk);
      for (i = 0; i < 50 && !arready; i = i + 1) @(posedge aclk);
      @(negedge aclk);
      arvalid = 0;
      i = 0;
      while (!rvalid && i < 50) begin
        @(posedge aclk);
        i = i + 1;
      end
      rd = rdata;
      @(negedge aclk);
    end
  endtask

  task send_trickle;
    begin
      k = 0;
      while (k < nbytes) begin
        @(negedge aclk);
        s_tdata  = {56'd0, pkt[k]};
        s_tkeep  = 8'h01;
        s_tvalid = 1;
        s_tlast  = ((k + 1) >= nbytes);
        @(posedge aclk);
        i = 0;
        while (!s_tready && i < 4000) begin
          @(posedge aclk);
          i = i + 1;
        end
        k = k + 1;
      end
      @(negedge aclk);
      s_tvalid = 0;
      s_tlast  = 0;
    end
  endtask

  initial begin
    pkt[0]=8'h4E; pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
    pkt[4]=8'h41; pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
    pkt[8]=8'h00; pkt[9]=8'h01;
    pkt[10]=8'h00; pkt[11]=8'h01;
    pkt[12]=8'h00; pkt[13]=8'h24;
    for (i = 0; i < 36; i = i + 1) pkt[14+i] = (i == 0) ? 8'h41 : (8'h10 + i[7:0]);
    nbytes = 50;

    // Gate-level: Xilinx primitives are held by the global set/reset from `glbl`, which asserts at
    // time 0 and releases after 100 ns by default. Releasing aresetn before that leaves every flop
    // held, and the design looks dead (awready never rises).
    aresetn = 0;
    wait (glbl.GSR === 1'b0);
    repeat (10) @(negedge aclk);
    aresetn = 1;
    repeat (10) @(negedge aclk);
    $display("GLS-PROBE reset released at t=%0t, GSR=%b", $time, glbl.GSR);

    axi_write(5'h18, 32'h1);
    repeat (3) @(negedge aclk);
    $display("GLS-PROBE after enable: awready=%b wready=%b s_tready=%b", awready, wready, s_tready);
    repeat (20) @(negedge aclk);
    $display("GLS-PROBE 20 cycles later: s_tready=%b", s_tready);

    send_trickle;
    repeat (400) @(negedge aclk);

    axi_read(5'h00);
    $display("GLS-TRICKLE rx_packets=%0d", rd);
    axi_read(5'h08);
    $display("GLS-TRICKLE rx_messages=%0d", rd);
    axi_read(5'h14);
    $display("GLS-TRICKLE err=%0d", rd);
    axi_read(5'h10);
    $display("GLS-TRICKLE gap=%0d", rd);

    $display("GLS-TRICKLE-DONE");
    $finish;
  end

endmodule
