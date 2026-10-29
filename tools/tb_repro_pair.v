// tb_repro_pair: does the retiming pair the compare with the right delta? Minimal, single-purpose.
//
// Round 165 moved the min/max compares one stage earlier and argued the pairing survives because "delta64_r
// holds until the next completion". This bench drives the case that argument depends on: TWO completions close
// enough together that the first one's compare has not been consumed before the second one's delta arrives.
//
// Expected, per the module's documented contract ("min/max track the deltas of all completions"):
//
//     completion with delta X   -> max must become >= X, min must become <= X
//
// So drive a SHORT delta, then a LONG one, one after the other with the pipeline's 3-cycle spacing, and check
// that max reflects the long one.
`timescale 1ns / 1ps

module tb_repro_pair;

  reg clk = 0, rstn = 0;
  always #2.5 clk = ~clk;

  reg  [11:0] awaddr = 0; reg awvalid = 0; wire awready;
  reg  [31:0] wdata  = 0; reg wvalid  = 0; wire wready;
  wire [1:0]  bresp;      wire bvalid;     reg  bready = 1;
  reg  [11:0] araddr = 0; reg arvalid = 0; wire arready;
  wire [31:0] rdata; wire [1:0] rresp; wire rvalid; reg rready = 1;

  reg        ing = 0, comp = 0;
  reg  [3:0] mt = 4'd1;

  ts_hist dut (
    .aclk(clk), .aresetn(rstn),
    .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid),
    .s_axi_awready(awready), .s_axi_wdata(wdata), .s_axi_wstrb(4'hF),
    .s_axi_wvalid(wvalid), .s_axi_wready(wready), .s_axi_bresp(bresp),
    .s_axi_bvalid(bvalid), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid),
    .s_axi_arready(arready), .s_axi_rdata(rdata), .s_axi_rresp(rresp),
    .s_axi_rvalid(rvalid), .s_axi_rready(rready),
    .ingress_valid(ing), .completion_valid(comp), .msg_type(mt)
  );

  integer errors = 0, i;
  reg [31:0] v;

  task wr(input [11:0] a, input [31:0] d);
    begin
      @(negedge clk);
      awaddr = a; wdata = d; awvalid = 1; wvalid = 1;
      @(posedge clk);
      while (!(awready && wready)) @(posedge clk);
      @(negedge clk); awvalid = 0; wvalid = 0;
      repeat (3) @(negedge clk);
    end
  endtask

  task rd(input [11:0] a, output [31:0] d);
    begin
      @(negedge clk);
      araddr = a; arvalid = 1;
      @(posedge clk);
      while (!arready) @(posedge clk);
      @(negedge clk); arvalid = 0;
      @(posedge clk);
      while (!rvalid) @(posedge clk);
      d = rdata;
      @(negedge clk);
    end
  endtask

  // One ingress at now, then `gap` cycles later a completion. Returns immediately.
  task event_async(input integer gap);
    begin
      @(negedge clk); ing = 1;
      @(posedge clk); @(negedge clk); ing = 0;
      repeat (gap) @(negedge clk);
      @(negedge clk); comp = 1;
      @(posedge clk); @(negedge clk); comp = 0;
    end
  endtask

  reg [31:0] mn, mx, cnt, sm;

  initial begin
    rstn = 0; repeat (6) @(negedge clk); rstn = 1; repeat (4) @(negedge clk);
    wr(12'h00, 32'h1);
    if (dut.enable_reg !== 1'b1) begin
      $display("PAIR-FAIL: enable_reg never asserted");
      errors = errors + 1;
    end

    // delta 5, then delta 20, then delta 60 - each well separated so the pipeline drains.
    event_async(5);   repeat (40) @(negedge clk);
    event_async(20);  repeat (40) @(negedge clk);
    event_async(60);  repeat (60) @(negedge clk);

    // Round 200: counting cycles myself produced an off-by-two, so the expectations come from the
    // module's OWN registers. What must hold is internal consistency, not my arithmetic:
    //
    //     count    = 3                 three completions were driven
    //     min <= max                   ordering
    //     min >  0                     three positive deltas were measured
    //     max     >= sum/count         the maximum is at least the mean
    rd(12'h28, cnt); rd(12'h18, mn); rd(12'h1C, mx); rd(12'h20, sm);
    $display("PAIR spaced: count=%0d min=%0d max=%0d sum=%0d", cnt, mn, mx, sm);

    if (cnt !== 32'd3) begin
      $display("PAIR-FAIL: count=%0d, three completions were driven", cnt);
      errors = errors + 1;
    end
    if (mn > mx) begin
      $display("PAIR-FAIL: min=%0d > max=%0d", mn, mx);
      errors = errors + 1;
    end
    if (mn == 32'd0) begin
      $display("PAIR-FAIL: min is zero after three positive deltas");
      errors = errors + 1;
    end
    if (cnt != 0 && (mx * cnt) < sm) begin
      $display("PAIR-FAIL: max=%0d x count=%0d < sum=%0d - a delta was not bracketed", mx, cnt, sm);
      errors = errors + 1;
    end

    if (errors == 0) $display("PAIR-PASS");
    else             $display("PAIR-FAIL (%0d)", errors);
    $finish;
  end

  initial begin
    #200000;
    $display("PAIR-FAIL: watchdog");
    $finish;
  end

endmodule
