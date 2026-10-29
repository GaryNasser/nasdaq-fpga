// tb_book_levels: can the book allocate every level the address space provides?
//
// Round 7 found an off-by-one in order_book.v:
//
//     allocate:   level_table[next_free_level] <= ...
//     guard:      if (next_free_level <  LEVELS - 1)      pointer stops at LEVELS-2
//     full test:  if (next_free_level >= LEVELS - 1)      declares full at LEVELS-1
//
// Indices 0..LEVELS-2 are used; index LEVELS-1 is never written. The declared capacity is never
// reachable, and the board's `level_cnt=255` against `LEVELS=256` is exactly that limit.
//
// With LEVELS = 8 this bench:
//   1  fills the book with 8 distinct prices on one side
//   2  requires all 8 to be allocated          (before the fix: 7)
//   3  requires the 9th to be dropped          (the table really is full)
`timescale 1ns / 1ps

module tb_book_levels;

    localparam LEVELS      = 8;
    localparam LEVEL_ADDR_W = 3;

    reg aclk = 0;
    always #2.5 aclk = ~aclk;

    reg aresetn;

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

    reg  [255:0] evt;
    reg          evt_valid;
    wire         evt_ready;
    reg  [15:0]  stock_locate;
    wire         busy;

    order_book #(
        .ORDERS(64),
        .LEVELS(LEVELS),
        .ORD_ADDR_W(6),
        .LEVEL_ADDR_W(LEVEL_ADDR_W)
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

    integer errors = 0;

    task axi_write(input [5:0] addr, input [31:0] data);
        begin
            @(posedge aclk);
            s_axi_awaddr  <= addr;
            s_axi_awvalid <= 1'b1;
            s_axi_wdata   <= data;
            s_axi_wvalid  <= 1'b1;
            while (!s_axi_awready) @(posedge aclk);
            s_axi_awvalid <= 1'b0;
            while (!s_axi_wready) @(posedge aclk);
            s_axi_wvalid  <= 1'b0;
            while (!s_axi_bvalid) @(posedge aclk);
            @(posedge aclk);
        end
    endtask

    task axi_read(input [5:0] addr, output [31:0] data);
        begin
            @(posedge aclk);
            s_axi_araddr  <= addr;
            s_axi_arvalid <= 1'b1;
            while (!s_axi_arready) @(posedge aclk);
            s_axi_arvalid <= 1'b0;
            @(posedge aclk);
            while (!s_axi_rvalid) @(posedge aclk);
            data = s_axi_rdata;
            s_axi_rready <= 1'b1;
            @(posedge aclk);
            s_axi_rready <= 1'b0;
        end
    endtask

    task send_add(input [31:0] price, input [63:0] order_ref);
        begin
            @(posedge aclk);
            evt <= { 3'd0,           // rsvd
                     8'h41,          // msg_type
                     48'd1000,       // timestamp
                     order_ref,      // order_ref
                     64'd0,          // aux_ref
                     price,          // price
                     32'd100,        // shares   (32 bits - a 64-bit literal here shifts every field)
                     1'b0,           // side: 0 = bid  (RTL: if (!ev_side))
                     4'd1            // act = add
                   };
            evt_valid   <= 1'b1;
            stock_locate <= 16'd1;
            while (!(evt_valid && evt_ready)) @(posedge aclk);
            evt_valid <= 1'b0;
            @(posedge aclk);
            while (busy) @(posedge aclk);
            @(posedge aclk);
        end
    endtask

    task check(input [31:0] actual, input [31:0] expected, input [8*44:0] name);
        begin
            if (actual !== expected) begin
                $display("[FAIL] %0s: got %0d, expected %0d", name, actual, expected);
                errors = errors + 1;
            end else begin
                $display("[PASS] %0s: %0d", name, actual);
            end
        end
    endtask

    reg [31:0] rdata;
    integer i;

    initial begin
        aresetn       = 1'b0;
        s_axi_awaddr  = 6'd0;  s_axi_awprot  = 3'd0;  s_axi_awvalid = 1'b0;
        s_axi_wdata   = 32'd0; s_axi_wstrb   = 4'hF;  s_axi_wvalid  = 1'b0;
        s_axi_bready  = 1'b1;
        s_axi_araddr  = 6'd0;  s_axi_arprot  = 3'd0;  s_axi_arvalid = 1'b0;
        s_axi_rready  = 1'b1;
        evt           = 256'd0; evt_valid    = 1'b0;  stock_locate  = 16'd1;

        repeat (8) @(posedge aclk);
        aresetn <= 1'b1;
        repeat (8) @(posedge aclk);

        // The book ignores events until CTRL bit0 is set.
        axi_write(6'h30, 32'h1);

        // LEVELS distinct bid prices -> LEVELS distinct levels.
        for (i = 0; i < LEVELS; i = i + 1) begin
            send_add(32'd10000 + i * 100, 64'd1000 + i);
            $display("  sent price=%0d ref=%0d", 32'd10000 + i * 100, 64'd1000 + i);
        end

        axi_read(6'h04, rdata);            // BOOK_LEVEL_CNT
        check(rdata, LEVELS, "level_cnt reaches the declared capacity");

        axi_read(6'h00, rdata);            // BOOK_ORDER_CNT
        check(rdata, LEVELS, "order_cnt");

        // The table is full: a further distinct price must be dropped, not allocated.
        send_add(32'd99999, 64'd9000);

        axi_read(6'h04, rdata);
        check(rdata, LEVELS, "level_cnt stays at capacity");

        axi_read(6'h2C, rdata);            // BOOK_DROP_CNT
        check(rdata, 32'd1, "the overflow add is dropped");

        $display("");
        if (errors == 0) $display("BOOK-LEVELS-PASS (%0d levels allocated, overflow dropped)", LEVELS);
        else             $display("BOOK-LEVELS-FAIL (%0d error(s))", errors);
        $finish;
    end

    initial begin
        #500000;
        $display("BOOK-LEVELS-FAIL (timeout)");
        $finish;
    end

endmodule
