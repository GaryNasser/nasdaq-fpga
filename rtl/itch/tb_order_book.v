// tb_order_book: self-checking testbench for order_book module.
//
// Tests: ADD (buy/sell), BBO update, EXECUTE (shares reduction),
//        level reuse (same price), DELETE, stats readback.
//
// Packs events into the 256-bit struct format matching itch_parse output:
//   [255:253] rsvd=0, [252:245] msg_type, [244:197] timestamp,
//   [196:133] order_ref, [132:69] aux_ref, [68:37] price,
//   [36:5] shares, [4] side, [3:0] act

`timescale 1ns / 1ps

module tb_order_book;

  reg         aclk;
  reg         aresetn;

  // AXI4-Lite
  reg  [5:0]  s_axi_awaddr;
  reg  [2:0]  s_axi_awprot;
  reg         s_axi_awvalid;
  wire        s_axi_awready;
  reg  [31:0] s_axi_wdata;
  reg  [3:0]  s_axi_wstrb;
  reg         s_axi_wvalid;
  wire        s_axi_wready;
  wire [1:0]  s_axi_bresp;
  wire        s_axi_bvalid;
  reg         s_axi_bready;
  reg  [5:0]  s_axi_araddr;
  reg  [2:0]  s_axi_arprot;
  reg         s_axi_arvalid;
  wire        s_axi_arready;
  wire [31:0] s_axi_rdata;
  wire [1:0]  s_axi_rresp;
  wire        s_axi_rvalid;
  reg         s_axi_rready;

  // Event input
  reg  [255:0] evt;
  reg          evt_valid;
  wire         evt_ready;
  reg  [15:0]  stock_locate;
  wire         busy;

  order_book #(
    .ORDERS(256),
    .LEVELS(32),
    .ORD_ADDR_W(8),
    .LEVEL_ADDR_W(5)
  ) dut (
    .aclk(aclk),
    .aresetn(aresetn),
    .s_axi_awaddr(s_axi_awaddr),
    .s_axi_awprot(s_axi_awprot),
    .s_axi_awvalid(s_axi_awvalid),
    .s_axi_awready(s_axi_awready),
    .s_axi_wdata(s_axi_wdata),
    .s_axi_wstrb(s_axi_wstrb),
    .s_axi_wvalid(s_axi_wvalid),
    .s_axi_wready(s_axi_wready),
    .s_axi_bresp(s_axi_bresp),
    .s_axi_bvalid(s_axi_bvalid),
    .s_axi_bready(s_axi_bready),
    .s_axi_araddr(s_axi_araddr),
    .s_axi_arprot(s_axi_arprot),
    .s_axi_arvalid(s_axi_arvalid),
    .s_axi_arready(s_axi_arready),
    .s_axi_rdata(s_axi_rdata),
    .s_axi_rresp(s_axi_rresp),
    .s_axi_rvalid(s_axi_rvalid),
    .s_axi_rready(s_axi_rready),
    .evt(evt),
    .evt_valid(evt_valid),
    .evt_ready(evt_ready),
    .stock_locate(stock_locate),
    .busy(busy)
  );

  // Clock: 200 MHz = 5 ns period
  initial aclk = 0;
  always #2.5 aclk = ~aclk;

  // ----------------------------------------------------------------------
  // AXI4-Lite tasks
  // ----------------------------------------------------------------------
  task axi_write(input [5:0] addr, input [31:0] data);
    begin
      @(posedge aclk);
      s_axi_awaddr  <= addr;
      s_axi_awvalid <= 1'b1;
      s_axi_wdata   <= data;
      s_axi_wstrb   <= 4'hF;
      s_axi_wvalid  <= 1'b1;
      // Wait for both ready
      while (!(s_axi_awready && s_axi_wready)) @(posedge aclk);
      s_axi_awvalid <= 1'b0;
      s_axi_wvalid  <= 1'b0;
      // Respond to B
      @(posedge aclk);
      while (!s_axi_bvalid) @(posedge aclk);
      s_axi_bready <= 1'b1;
      @(posedge aclk);
      s_axi_bready <= 1'b0;
    end
  endtask

  task axi_read(input [5:0] addr, output [31:0] data);
    begin
      @(posedge aclk);
      s_axi_araddr  <= addr;
      s_axi_arvalid <= 1'b1;
      while (!s_axi_arready) @(posedge aclk);
      s_axi_arvalid <= 1'b0;
      // Wait for read data
      @(posedge aclk);
      while (!s_axi_rvalid) @(posedge aclk);
      data = s_axi_rdata;
      s_axi_rready <= 1'b1;
      @(posedge aclk);
      s_axi_rready <= 1'b0;
    end
  endtask

  // ----------------------------------------------------------------------
  // Event send task
  // ----------------------------------------------------------------------
  task send_event(input [3:0] act, input side, input [31:0] price,
                  input [31:0] shares, input [63:0] order_ref);
    begin
      @(posedge aclk);
      evt <= { 3'd0,           // rsvd [255:253]
               8'h41,          // msg_type [252:245] (doesn't matter for book)
               48'd1000,       // timestamp [244:197]
               order_ref,      // order_ref [196:133]
               64'd0,          // aux_ref [132:69]
               price,          // price [68:37]
               shares,         // shares [36:5]
               side,           // side [4]
               act             // act [3:0]
             };
      evt_valid   <= 1'b1;
      stock_locate <= 16'd1;
      // Wait for handshake (evt_ready) — FSM accepts the event
      while (!(evt_valid && evt_ready)) @(posedge aclk);
      evt_valid <= 1'b0;
      // Wait for FSM to finish processing (busy goes low)
      // The search scans up to LEVELS entries, so this may take ~100 cycles.
      @(posedge aclk);
      while (busy) @(posedge aclk);
      @(posedge aclk);
    end
  endtask

  // ----------------------------------------------------------------------
  // Check task
  // ----------------------------------------------------------------------
  integer errors;
  task check(input [31:0] actual, input [31:0] expected, input [8*31:0] name);
    begin
      if (actual !== expected) begin
        $display("[FAIL] %0s: got %0d, expected %0d", name, actual, expected);
        errors = errors + 1;
      end else begin
        $display("[PASS] %0s: %0d", name, actual);
      end
    end
  endtask

  // ----------------------------------------------------------------------
  // Main test
  // ----------------------------------------------------------------------
  reg [31:0] rdata;

  initial begin
    // Init
    aresetn     = 1'b0;
    s_axi_awaddr = 6'd0; s_axi_awprot = 3'd0; s_axi_awvalid = 1'b0;
    s_axi_wdata  = 32'd0; s_axi_wstrb = 4'hF; s_axi_wvalid = 1'b0;
    s_axi_bready = 1'b0;
    s_axi_araddr = 6'd0; s_axi_arprot = 3'd0; s_axi_arvalid = 1'b0;
    s_axi_rready = 1'b0;
    evt = 256'd0; evt_valid = 1'b0; stock_locate = 16'd0;
    errors = 0;

    // Reset
    repeat(10) @(posedge aclk);
    aresetn = 1'b1;
    repeat(5) @(posedge aclk);

    // Enable the book
    axi_write(6'h30, 32'h1);  // CTRL = enable

    // Test 1: ADD buy order (price 100, shares 1000, ref 1)
    send_event(4'd1, 1'b0, 32'd100, 32'd1000, 64'd1);

    // Test 2: ADD sell order (price 101, shares 500, ref 2)
    send_event(4'd1, 1'b1, 32'd101, 32'd500, 64'd2);

    // Check BBO
    axi_read(6'h08, rdata); check(rdata, 32'd100, "BID_PRICE");   // bid = 100
    axi_read(6'h0C, rdata); check(rdata, 32'd1000, "BID_SHARES"); // bid shares = 1000
    axi_read(6'h10, rdata); check(rdata, 32'd101, "ASK_PRICE");   // ask = 101
    axi_read(6'h14, rdata); check(rdata, 32'd500, "ASK_SHARES");  // ask shares = 500

    // Check order count
    axi_read(6'h00, rdata); check(rdata, 32'd2, "ORDER_CNT");    // 2 orders

    // Check level count (2 levels: bid 100, ask 101)
    axi_read(6'h04, rdata); check(rdata, 32'd2, "LEVEL_CNT");    // 2 levels

    // Test 3: ADD another buy at same price (reuse level)
    send_event(4'd1, 1'b0, 32'd100, 32'd200, 64'd3);
    axi_read(6'h0C, rdata); check(rdata, 32'd1200, "BID_SHARES_AFTER_REUSE"); // 1000+200
    axi_read(6'h04, rdata); check(rdata, 32'd2, "LEVEL_CNT_AFTER_REUSE");    // still 2 levels
    axi_read(6'h00, rdata); check(rdata, 32'd3, "ORDER_CNT_AFTER_REUSE");   // 3 orders

    // Test 4: EXECUTE buy order ref 1 (reduce shares 200)
    send_event(4'd2, 1'b0, 32'd0, 32'd200, 64'd1);
    // After execute, order_ref 1 is invalidated. Bid shares should be 1200-200=1000
    // (the level still has order 3's shares = 200, but order 1's 1000-200=800 removed)
    // Actually: level had 1200 (1000 from ref1 + 200 from ref3). Execute ref1 removes 200.
    // Level now has 1000 shares.
    axi_read(6'h0C, rdata); check(rdata, 32'd1000, "BID_SHARES_AFTER_EXEC");

    // Test 5: DELETE order ref 3
    send_event(4'd4, 1'b0, 32'd0, 32'd0, 64'd3);
    axi_read(6'h00, rdata); check(rdata, 32'd1, "ORDER_CNT_AFTER_DEL"); // 3-1-1=1 (ref2 only; ref1 executed, ref3 deleted)

    // Check stats
    axi_read(6'h18, rdata); check(rdata, 32'd3, "ADD_CNT");
    axi_read(6'h1C, rdata); check(rdata, 32'd1, "EXE_CNT");
    axi_read(6'h24, rdata); check(rdata, 32'd1, "DEL_CNT");

    // Final
    if (errors == 0)
      $display("TB-ALL-PASS");
    else
      $display("TB-FAIL: %0d errors", errors);

    $finish;
  end

endmodule
