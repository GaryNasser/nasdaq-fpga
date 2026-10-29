// tb_parser_tlast: drive the parser with 49 messages and count how often msg_latched sets.
//
// Round 140's contradiction: rx_messages=49 on the board requires out_last to have risen 49 times,
// which requires msg_latched to set 49 times, which requires one of the three counters to fire.
// All three are zero.
//
// This drives the parser directly with a synthetic MoldUDP64-style message stream - 49 messages,
// each with tlast on its final byte - and counts msg_latched risings and the three counters.
//
// If msg_latched rises 49 times and parse_cnt rises with it, the parser is correct and the board's
// difference is in the tlast it receives. If msg_latched never rises, the parser's in_last_r path
// never sees tlast and the contradiction is a parser bug.
`timescale 1ns / 1ps

module tb_parser_tlast;

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

  // Count msg_latched risings.
  reg prev_latch = 0;
  integer latch_rises = 0;
  always @(posedge aclk) begin
    if (aresetn && dut.msg_latched && !prev_latch) latch_rises <= latch_rises + 1;
    prev_latch <= dut.msg_latched;
  end

  integer i;
  integer k;
  // 49 messages, each a 2-byte length prefix + a 36-byte Add Order (type 'A').
  // The parser consumes bytes from tdata[7:0], one per accepted beat.
  reg [7:0] stream [0:4095];
  integer   nbytes;

  initial begin
    // Build: for each of 49 messages, prefix 0x0024 then 36 bytes starting with 'A'.
    nbytes = 0;
    for (i = 0; i < 49; i = i + 1) begin
      stream[nbytes]     = 8'h00;
      stream[nbytes + 1] = 8'h24;
      nbytes = nbytes + 2;
      for (k = 0; k < 36; k = k + 1)
        stream[nbytes + k] = (k == 0) ? 8'h41 : (8'h10 + (k[7:0]));
      nbytes = nbytes + 36;
    end

    aresetn = 0;
    repeat (10) @(negedge aclk);
    aresetn = 1;
    repeat (5) @(negedge aclk);

    @(negedge aclk);
    awaddr = 5'h14; wdata = 32'h1; awvalid = 1; wvalid = 1;
    @(posedge aclk);
    for (i = 0; i < 50 && !(awready && wready); i = i + 1) @(posedge aclk);
    @(negedge aclk);
    awvalid = 0; wvalid = 0;
    repeat (5) @(negedge aclk);

    // Drive: one byte per beat, tlast on the last byte of each message.
    k = 0;
    i = 0;
    while (k < nbytes) begin
      @(negedge aclk);
      s_tdata  = {56'd0, stream[k]};
      s_tlast  = ((k + 1) % 38) == 0;   // every 38 bytes completes a message
      s_tvalid = 1;
      @(posedge aclk);
      while (!s_tready) begin
        @(posedge aclk);
      end
      k = k + 1;
    end
    @(negedge aclk);
    s_tvalid = 0;
    s_tlast  = 0;

    repeat (2000) @(negedge aclk);

    $display("PTLAST latch_rises=%0d parse_cnt=%0d drop_len=%0d err_type=%0d",
             latch_rises, dut.parse_cnt, dut.drop_len_cnt, dut.err_type_cnt);
    if (latch_rises == 0)
      $display("PTLAST-FAIL-NO-LATCH: tlast never latched a message");
    else if (dut.parse_cnt == 0)
      $display("PTLAST-FAIL-NO-PARSE: messages latched but none parsed");
    else
      $display("PTLAST-OK: parser latched and parsed the stream");

    $finish;
  end

endmodule
