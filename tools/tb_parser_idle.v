// tb_parser_idle: enable the parser and idle BEFORE sending anything.
//
// Round 138 measured on hardware: parse_cnt, drop_len and err_type are all zero while the
// reassembler reports 49 messages. The parser produced no observable action.
//
// Its handshake is `s_axis_tready = enable && !msg_latched`, so if msg_latched is set while idle
// the parser refuses every byte and all three counters stay zero.
//
// Every existing bench sends a packet immediately after enabling, so a latch wrongly set during
// reset would be masked.
`timescale 1ns / 1ps

module tb_parser_idle;

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

  wire [255:0] evt;
  wire         evt_valid;
  reg          evt_ready = 1;
  wire [15:0]  stock_locate;

  itch_parse dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid),
    .s_axi_awready(awready), .s_axi_wdata(wdata), .s_axi_wstrb(4'hF),
    .s_axi_wvalid(wvalid), .s_axi_wready(wready), .s_axi_bresp(bresp),
    .s_axi_bvalid(bvalid), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid),
    .s_axi_arready(arready), .s_axi_rdata(rdata), .s_axi_rresp(rresp),
    .s_axi_rvalid(rvalid), .s_axi_rready(rready),
    .s_axis_tdata(s_tdata), .s_axis_tkeep(s_tkeep), .s_axis_tvalid(s_tvalid),
    .s_axis_tready(s_tready), .s_axis_tlast(s_tlast),
    .evt(evt), .evt_valid(evt_valid), .evt_ready(evt_ready),
    .stock_locate(stock_locate)
  );

  integer i;
  integer latched_cycles;
  integer not_ready_cycles;

  initial begin
    aresetn = 0;
    repeat (10) @(negedge aclk);
    aresetn = 1;
    repeat (5) @(negedge aclk);

    // Enable through AXI-Lite CTRL at 0x14 (index 5).
    @(negedge aclk);
    awaddr = 5'h14; wdata = 32'h1;   // 0x14 = ADDR_CTRL << 2
    awvalid = 1; wvalid = 1;
    @(posedge aclk);
    for (i = 0; i < 50 && !(awready && wready); i = i + 1) @(posedge aclk);
    if (!(awready && wready))
      $display("PIDLE-AXI-STUCK awready=%b wready=%b", awready, wready);
    @(negedge aclk);
    awvalid = 0; wvalid = 0;

    // Idle with NOTHING sent - the state the board is in while the DMA is set up.
    latched_cycles = 0;
    not_ready_cycles = 0;
    for (i = 0; i < 200; i = i + 1) begin
      @(negedge aclk);
      if (dut.msg_latched) latched_cycles = latched_cycles + 1;
      if (!s_tready) not_ready_cycles = not_ready_cycles + 1;
    end

    $display("PIDLE latched=%0d/200 not_ready=%0d/200 msg_latched=%b tready=%b enable=%b",
             latched_cycles, not_ready_cycles, dut.msg_latched, s_tready, dut.enable);

    if (latched_cycles > 0 || not_ready_cycles > 0)
      $display("PIDLE-DIAG-FAIL-LATCHED: the parser refuses input while idle");
    else
      $display("PIDLE-CLEAN: the parser is ready while idle");

    $finish;
  end

endmodule
