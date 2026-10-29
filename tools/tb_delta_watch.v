// tb_delta_watch: record every delta64_r the module commits, and compare that list to sum/count/max.
//
// The invariant max*count >= sum is violated, so `gt_max_r` refuses deltas that `sum_delta` accepts. Rather than
// reason about why, RECORD the deltas: sum must equal their sum, count their number, min/max their extremes.
// That pins the defect to a specific value instead of a mechanism.
`timescale 1ns / 1ps

module tb_delta_watch;

  reg clk = 0, rstn = 0;
  always #2.5 clk = ~clk;

  reg  [11:0] awaddr = 0; reg awvalid = 0; wire awready;
  reg  [31:0] wdata  = 0; reg wvalid  = 0; wire wready;
  wire [1:0]  bresp;      wire bvalid;     reg  bready = 1;
  reg  [11:0] araddr = 0; reg arvalid = 0; wire arready;
  wire [31:0] rdata; wire [1:0] rresp; wire rvalid; reg rready = 1;

  reg ing = 0, comp = 0;
  reg [3:0] mt = 4'd1;

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

  // Capture every delta the STAGE-2 block accepts (the cycle count_delta increments).
  integer n_cap = 0;
  integer cap [0:15];
  always @(posedge clk) begin
    if (rstn && dut.completion_r) begin
      cap[n_cap] = dut.delta64_r;
      n_cap = n_cap + 1;
    end
  end

  integer i, k;
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

  task ev(input integer gap);
    begin
      @(negedge clk); ing = 1;
      @(posedge clk); @(negedge clk); ing = 0;
      repeat (gap) @(negedge clk);
      @(negedge clk); comp = 1;
      @(posedge clk); @(negedge clk); comp = 0;
    end
  endtask

  integer expect_sum, expect_min, expect_max;

  initial begin
    rstn = 0; repeat (6) @(negedge clk); rstn = 1; repeat (4) @(negedge clk);
    wr(12'h00, 32'h1);
    ev(5);  repeat (50) @(negedge clk);
    ev(20); repeat (50) @(negedge clk);
    ev(60); repeat (80) @(negedge clk);

    $display("WATCH captured deltas: n=%0d", n_cap);
    expect_sum = 0; expect_min = 1000000; expect_max = 0;
    for (i = 0; i < n_cap; i = i + 1) begin
      $display("   delta[%0d] = %0d", i, cap[i]);
      expect_sum = expect_sum + cap[i];
      if (cap[i] < expect_min) expect_min = cap[i];
      if (cap[i] > expect_max) expect_max = cap[i];
    end

    rd(12'h28, v); $display("WATCH module count=%0d  captured=%0d", v, n_cap);
    rd(12'h20, v); $display("WATCH module sum  =%0d  captured sum=%0d", v, expect_sum);
    rd(12'h18, v); $display("WATCH module min  =%0d  captured min=%0d", v, expect_min);
    rd(12'h1C, v); $display("WATCH module max  =%0d  captured max=%0d", v, expect_max);
    $finish;
  end

  initial begin
    #200000; $finish;
  end

endmodule
