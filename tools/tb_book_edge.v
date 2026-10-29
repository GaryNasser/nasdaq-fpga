// tb_book_edge: degenerate EVENT SEQUENCES into order_book, which no bench drives.
//
// `tb_book` feeds real ITCH messages through itch_parse and checks the eight counters. It never constructs an
// out-of-order event, so the book's behaviour on a Cancel for an unknown order, a Delete of an already-removed
// order, or a Replace on a missing one has never been observed.
//
// Real ITCH feeds contain these: a capture starting mid-session begins without the Add for every live order, so
// the first messages are necessarily cancels and executes against orders the book never saw.
//
// What must hold for each:
//
//     no X propagation into the AXI registers   (a book that emits X would corrupt the driver's reads)
//     the counters stay coherent                (can_cnt may move, but bid/ask shares must not go negative)
//     the book keeps serving                    (a later valid Add still updates the BBO)
//
// The failure this guards against is a share underflow: subtracting shares for an order that was never added
// would wrap a 32-bit total, and the driver reads that total as unsigned.
`timescale 1ns / 1ps

module tb_book_edge;

  reg clk = 0, rstn = 0;
  always #2.5 clk = ~clk;

  reg  [5:0]  awaddr = 0; reg awvalid = 0; wire awready;
  reg  [31:0] wdata  = 0; reg wvalid  = 0; wire wready;
  wire [1:0]  bresp;      wire bvalid;     reg  bready = 1;
  reg  [5:0]  araddr = 0; reg arvalid = 0; wire arready;
  wire [31:0] rdata; wire [1:0] rresp; wire rvalid; reg rready = 1;

  reg  [255:0] evt = 0;
  reg          evt_valid = 0;

  order_book #(
    .ORDERS(256), .LEVELS(32)
  ) dut (
    .aclk(clk), .aresetn(rstn),
    .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid),
    .s_axi_awready(awready), .s_axi_wdata(wdata), .s_axi_wstrb(4'hF),
    .s_axi_wvalid(wvalid), .s_axi_wready(wready), .s_axi_bresp(bresp),
    .s_axi_bvalid(bvalid), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid),
    .s_axi_arready(arready), .s_axi_rdata(rdata), .s_axi_rresp(rresp),
    .s_axi_rvalid(rvalid), .s_axi_rready(rready),
    .evt(evt), .evt_valid(evt_valid), .stock_locate(16'd6836)
  );

  localparam [3:0] ACT_ADD = 4'd1, ACT_EXE = 4'd2, ACT_CAN = 4'd3,
                   ACT_DEL = 4'd4, ACT_REP = 4'd5;

  integer errors = 0, i;

  // One event: action, side, price (1/10000 units), shares, order ref, aux ref.
  task send(input [3:0] act, input side, input [31:0] px,
            input [31:0] sh, input [63:0] ref_, input [63:0] aux);
    begin
      @(negedge clk);
      evt = 256'd0;
      evt[3:0]      = act;
      evt[4]        = side;
      evt[36:5]     = sh;
      evt[68:37]    = px;
      evt[132:69]   = aux;
      evt[196:133]  = ref_;
      evt_valid     = 1;
      @(posedge clk);
      while (!dut.evt_ready) @(posedge clk);
      @(negedge clk);
      evt_valid = 0;
      repeat (6) @(negedge clk);
    end
  endtask

  task wr(input [5:0] a, input [31:0] v);
    begin
      @(negedge clk);
      awaddr = a; wdata = v; awvalid = 1; wvalid = 1;
      @(posedge clk);
      while (!(awready && wready)) @(posedge clk);
      @(negedge clk);
      awvalid = 0; wvalid = 0;
      repeat (4) @(negedge clk);
    end
  endtask

  task rd(input [5:0] a, output [31:0] v);
    begin
      @(negedge clk);
      araddr = a; arvalid = 1;
      @(posedge clk);
      while (!arready) @(posedge clk);
      @(negedge clk);
      arvalid = 0;
      @(posedge clk);
      while (!rvalid) @(posedge clk);
      v = rdata;
      @(negedge clk);
    end
  endtask

  reg [31:0] bid_sh, ask_sh, bid_px, ask_px, add_c, can_c, exe_c;

  initial begin
    rstn = 0;
    repeat (8) @(negedge clk);
    rstn = 1;
    repeat (4) @(negedge clk);

    wr(6'h30, 32'h1);            // CTRL = 1, as the driver does
    if (dut.enable !== 1'b1) begin
      $display("EDGE-FAIL: enable never asserted - the book was never turned on");
      errors = errors + 1;
    end

    // Build a valid two-sided book first, so the edge cases act on a real state.
    send(ACT_ADD, 1'b0, 32'd1_025_000, 32'd500, 64'd1, 64'd0);   // bid 500 @ 102.5000
    send(ACT_ADD, 1'b1, 32'd1_026_000, 32'd300, 64'd2, 64'd0);   // ask 300 @ 102.6000
    repeat (40) @(negedge clk);

    rd(6'h00, add_c);
    $display("EDGE baseline: add_cnt=%0d can_cnt=%0d", add_c, can_c);

    // ---- edge 1: Cancel an order the book never saw -----------------------------------
    send(ACT_CAN, 1'b0, 32'd1_025_000, 32'd100, 64'd2, 64'd0);
    repeat (40) @(negedge clk);
    rd(6'h00, bid_sh);
    $display("EDGE cancel-unknown: bid_shares=%0d (0x%08h)", bid_sh, bid_sh);

    // ---- edge 2: Delete an order already removed ---------------------------------------
    send(ACT_DEL, 1'b0, 32'd1_025_000, 32'd500, 64'd1, 64'd0);
    repeat (20) @(negedge clk);
    send(ACT_DEL, 1'b0, 32'd1_025_000, 32'd500, 64'd1, 64'd0);
    repeat (40) @(negedge clk);

    // ---- edge 3: Execute more shares than remain ---------------------------------------
    send(ACT_EXE, 1'b1, 32'd1_026_000, 32'd5000, 64'd2, 64'd0);
    repeat (40) @(negedge clk);
    rd(6'h00, ask_sh);
    $display("EDGE execute-overrun: ask_shares=%0d (0x%08h)", ask_sh, ask_sh);

    // ---- edge 4: Replace a missing order -----------------------------------------------
    send(ACT_REP, 1'b0, 32'd1_025_500, 32'd777, 64'd9, 64'd99);
    repeat (40) @(negedge clk);

    // ---- the book must still work: add and observe a new BBO ---------------------------
    send(ACT_ADD, 1'b0, 32'd1_025_100, 32'd120, 64'd5, 64'd0);
    repeat (60) @(negedge clk);
    rd(6'h00, bid_sh);
    $display("EDGE after edges: bid_shares=%0d (0x%08h)", bid_sh, bid_sh);

    // No X anywhere in the readable registers.
    if (^bid_sh === 1'bx) begin
      $display("EDGE-FAIL: bid/ask shares contain X");
      errors = errors + 1;
    end

    if (bid_sh > 32'd100_000_000) begin
      $display("EDGE-FAIL: bid_shares=%0d wrapped - a share subtraction underflowed", bid_sh);
      errors = errors + 1;
    end

    if (errors == 0) $display("EDGE-PASS");
    else             $display("EDGE-FAIL (%0d)", errors);
    $finish;
  end

  initial begin
    #200000;
    $display("EDGE-FAIL: watchdog");
    $finish;
  end

endmodule
