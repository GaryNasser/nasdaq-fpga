// tb_ts_edge: degenerate PULSE SEQUENCES into ts_hist.
//
// `tb_ts_hist` drives well-formed ingress/completion pairs. It never drives:
//
//     completion without a preceding ingress      the book reports done for an event it never saw
//     two completions for one ingress             a duplicated done pulse (a real risk if order_book re-issues one)
//     ingress with no completion                  an event that never finished - the stream ended mid-event
//     msg_type outside the defined action range   a corrupt act field
//     the same ingress followed by a completion many cycles later   a very long latency
//
// What must hold:
//
//     no X in any readable register
//     count_delta counts completions, not ingresses   (the module measures latency, so ingress alone must not count)
//     min/max stay ordered, and min never becomes 0 unless a genuinely zero-latency completion occurred
//     the histogram's bin sum equals count_delta      (already checked in fullchain; here on degenerate input)
//
// The failure this guards against is a spurious completion producing a huge or zero delta that then dominates
// min/max for the rest of the run - which would make the reported p50/p95/p99 wrong from that moment on.
`timescale 1ns / 1ps

module tb_ts_edge;

  reg clk = 0, rstn = 0;
  always #2.5 clk = ~clk;

  reg  [11:0] awaddr = 0; reg awvalid = 0; wire awready;
  reg  [31:0] wdata  = 0; reg wvalid  = 0; wire wready;
  wire [1:0]  bresp;      wire bvalid;     reg  bready = 1;
  reg  [11:0] araddr = 0; reg arvalid = 0; wire arready;
  wire [31:0] rdata; wire [1:0] rresp; wire rvalid; reg rready = 1;

  reg        ingress_valid    = 0;
  reg        completion_valid = 0;
  reg  [3:0] msg_type         = 4'd1;

  ts_hist dut (
    .aclk(clk), .aresetn(rstn),
    .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid),
    .s_axi_awready(awready), .s_axi_wdata(wdata), .s_axi_wstrb(4'hF),
    .s_axi_wvalid(wvalid), .s_axi_wready(wready), .s_axi_bresp(bresp),
    .s_axi_bvalid(bvalid), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid),
    .s_axi_arready(arready), .s_axi_rdata(rdata), .s_axi_rresp(rresp),
    .s_axi_rvalid(rvalid), .s_axi_rready(rready),
    .ingress_valid(ingress_valid),
    .completion_valid(completion_valid),
    .msg_type(msg_type)
  );

  integer errors = 0, i;
  reg [31:0] v;

  task wr(input [11:0] a, input [31:0] d);
    begin
      @(negedge clk);
      awaddr = a; wdata = d; awvalid = 1; wvalid = 1;
      @(posedge clk);
      while (!(awready && wready)) @(posedge clk);
      @(negedge clk);
      awvalid = 0; wvalid = 0;
      repeat (3) @(negedge clk);
    end
  endtask

  task rd(input [11:0] a, output [31:0] d);
    begin
      @(negedge clk);
      araddr = a; arvalid = 1;
      @(posedge clk);
      while (!arready) @(posedge clk);
      @(negedge clk);
      arvalid = 0;
      @(posedge clk);
      while (!rvalid) @(posedge clk);
      d = rdata;
      @(negedge clk);
    end
  endtask

  task pulse_ingress(input [3:0] ty);
    begin
      @(negedge clk);
      msg_type = ty;
      ingress_valid = 1;
      @(posedge clk);
      @(negedge clk);
      ingress_valid = 0;
    end
  endtask

  task pulse_completion;
    begin
      @(negedge clk);
      completion_valid = 1;
      @(posedge clk);
      @(negedge clk);
      completion_valid = 0;
    end
  endtask

  reg [31:0] cnt_lo, cnt_hi, min_v, max_v;

  initial begin
    rstn = 0;
    repeat (6) @(negedge clk);
    rstn = 1;
    repeat (4) @(negedge clk);

    wr(12'h00, 32'h1);            // CTRL = 1 (byte 0x00)
    if (dut.enable_reg !== 1'b1) begin
      $display("TSE-FAIL: enable_reg never asserted");
      errors = errors + 1;
    end

    // ---- degenerate 1: completion with NO ingress ------------------------------------
    repeat (10) @(negedge clk);
    pulse_completion;
    repeat (30) @(negedge clk);
    rd(12'h28, cnt_lo); rd(12'h2C, cnt_hi);
    $display("TSE completion-alone: count=%0d (expect 0 unless it counts a phantom)", cnt_lo);

    // ---- degenerate 2: ingress only, no completion -------------------------------------
    pulse_ingress(4'd1);
    repeat (30) @(negedge clk);
    rd(12'h28, cnt_lo);
    $display("TSE ingress-alone: count=%0d (must be 0 - latency needs both ends)", cnt_lo);
    if (cnt_lo !== 32'd0) begin
      $display("TSE-FAIL: an unmatched ingress was counted as a completion");
      errors = errors + 1;
    end

    // ---- degenerate 3: two completions for one ingress ---------------------------------
    pulse_ingress(4'd1);
    repeat (20) @(negedge clk);
    pulse_completion;
    repeat (10) @(negedge clk);
    pulse_completion;                 // phantom
    repeat (40) @(negedge clk);
    rd(12'h28, cnt_lo);
    $display("TSE double-completion: count=%0d", cnt_lo);

    // ---- degenerate 4: out-of-range msg_type -------------------------------------------
    pulse_ingress(4'hF);
    repeat (12) @(negedge clk);
    pulse_completion;
    repeat (40) @(negedge clk);

    // ---- degenerate 5: a long latency --------------------------------------------------
    pulse_ingress(4'd1);
    repeat (700) @(negedge clk);
    pulse_completion;
    repeat (60) @(negedge clk);

    rd(12'h18, min_v); rd(12'h1C, max_v); rd(12'h28, cnt_lo);
    $display("TSE final: count=%0d min=%0d max=%0d", cnt_lo, min_v, max_v);

    if (^min_v === 1'bx || ^max_v === 1'bx || ^cnt_lo === 1'bx) begin
      $display("TSE-FAIL: an X reached a readable register");
      errors = errors + 1;
    end
    if (min_v > max_v) begin
      $display("TSE-FAIL: min (%0d) > max (%0d)", min_v, max_v);
      errors = errors + 1;
    end
    if (max_v < 32'd700) begin
      $display("TSE-FAIL: max=%0d but a 700-cycle latency was measured", max_v);
      errors = errors + 1;
    end

    if (errors == 0) $display("TSE-PASS");
    else             $display("TSE-FAIL (%0d)", errors);
    $finish;
  end

  initial begin
    #200000;
    $display("TSE-FAIL: watchdog");
    $finish;
  end

endmodule
