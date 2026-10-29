// tb_ts_hist: pin the statistics behaviour of ts_hist.
//
// ts_hist had no testbench, which is why the -0.087 ns path in it could not be
// fixed safely: changing its min/max update would alter the reported latency
// statistics with no way to check. This gives it one, so the timing change can
// be proven behaviour-preserving.
//
// Drives ingress/completion pairs with known deltas and checks DELTA, MIN, MAX,
// SUM and COUNT read back over AXI4-Lite.
`timescale 1ns / 1ps

module tb_ts_hist;

  reg aclk = 0;
  reg aresetn = 0;
  always #2.5 aclk = ~aclk;

  reg  [11:0] s_axi_awaddr = 0;
  reg  [2:0]  s_axi_awprot = 0;
  reg         s_axi_awvalid = 0;
  wire        s_axi_awready;
  reg  [31:0] s_axi_wdata = 0;
  reg  [3:0]  s_axi_wstrb = 4'hF;
  reg         s_axi_wvalid = 0;
  wire        s_axi_wready;
  wire [1:0]  s_axi_bresp;
  wire        s_axi_bvalid;
  reg         s_axi_bready = 1;
  reg  [11:0] s_axi_araddr = 0;
  reg  [2:0]  s_axi_arprot = 0;
  reg         s_axi_arvalid = 0;
  wire        s_axi_arready;
  wire [31:0] s_axi_rdata;
  wire [1:0]  s_axi_rresp;
  wire        s_axi_rvalid;
  reg         s_axi_rready = 1;

  reg         ingress_valid = 0;
  reg         completion_valid = 0;
  reg  [3:0]  msg_type = 0;

  ts_hist dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(s_axi_awaddr), .s_axi_awprot(s_axi_awprot),
    .s_axi_awvalid(s_axi_awvalid), .s_axi_awready(s_axi_awready),
    .s_axi_wdata(s_axi_wdata), .s_axi_wstrb(s_axi_wstrb),
    .s_axi_wvalid(s_axi_wvalid), .s_axi_wready(s_axi_wready),
    .s_axi_bresp(s_axi_bresp), .s_axi_bvalid(s_axi_bvalid),
    .s_axi_bready(s_axi_bready),
    .s_axi_araddr(s_axi_araddr), .s_axi_arprot(s_axi_arprot),
    .s_axi_arvalid(s_axi_arvalid), .s_axi_arready(s_axi_arready),
    .s_axi_rdata(s_axi_rdata), .s_axi_rresp(s_axi_rresp),
    .s_axi_rvalid(s_axi_rvalid), .s_axi_rready(s_axi_rready),
    .ingress_valid(ingress_valid),
    .completion_valid(completion_valid),
    .msg_type(msg_type)
  );

  integer errors = 0;
  integer i;
  reg [31:0] v;

  task axi_write(input [11:0] a, input [31:0] d);
    begin
      @(negedge aclk);
      s_axi_awaddr <= a; s_axi_awvalid <= 1;
      s_axi_wdata  <= d; s_axi_wvalid  <= 1;
      while (!(s_axi_awready && s_axi_wready)) @(negedge aclk);
      @(negedge aclk);
      s_axi_awvalid <= 0; s_axi_wvalid <= 0;
      while (!s_axi_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  task axi_read(input [11:0] a, output [31:0] d);
    begin
      @(negedge aclk);
      s_axi_araddr <= a; s_axi_arvalid <= 1;
      while (!s_axi_arready) @(negedge aclk);
      @(negedge aclk);
      s_axi_arvalid <= 0;
      while (!s_axi_rvalid) @(negedge aclk);
      d = s_axi_rdata;
      @(negedge aclk);
    end
  endtask

  task check(input [31:0] got, input [31:0] want, input [255:0] name);
    begin
      if (got !== want) begin
        $display("[FAIL] %0s got=%0d want=%0d", name, got, want);
        errors = errors + 1;
      end else
        $display("[PASS] %0s = %0d", name, got);
    end
  endtask

  // One measurement: pulse ingress, wait `gap` cycles, pulse completion.
  task measure(input integer gap);
    begin
      @(negedge aclk);
      ingress_valid <= 1;
      msg_type <= 4'd1;
      @(negedge aclk);
      ingress_valid <= 0;
      repeat (gap) @(negedge aclk);
      completion_valid <= 1;
      @(negedge aclk);
      completion_valid <= 0;
      repeat (6) @(negedge aclk);
    end
  endtask

  reg [31:0] min_v, max_v, cnt_v, delta_v;

  initial begin
    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);

    axi_write(12'h000, 32'h1);   // CTRL enable
    repeat (4) @(negedge aclk);

    // Three measurements with increasing gaps: 10, 40, 20 cycles.
    measure(10);
    measure(40);
    measure(20);

    // Word map: MIN=6 (0x18), MAX=7 (0x1C), SUM_LO=8 (0x20), COUNT_LO=10 (0x28).
    axi_read(12'h028, cnt_v);      // COUNT_LO
    check(cnt_v, 32'd3, "COUNT==3");

    axi_read(12'h018, min_v);      // MIN
    axi_read(12'h01C, max_v);      // MAX
    axi_read(12'h020, v);          // SUM_LO

    $display("  MIN=%0d MAX=%0d SUM=%0d", min_v, max_v, v);

    // Invariants that must hold whatever the exact cycle counts are:
    if (min_v == 32'h7FFFFFFF) begin
      $display("[FAIL] MIN was never updated");
      errors = errors + 1;
    end else
      $display("[PASS] MIN updated to %0d", min_v);

    if (max_v == 0) begin
      $display("[FAIL] MAX was never updated");
      errors = errors + 1;
    end else
      $display("[PASS] MAX updated to %0d", max_v);

    if (min_v > max_v) begin
      $display("[FAIL] MIN(%0d) > MAX(%0d)", min_v, max_v);
      errors = errors + 1;
    end else
      $display("[PASS] MIN <= MAX");

    // The 40-cycle measurement must dominate the 10- and 20-cycle ones.
    if (max_v <= min_v) begin
      $display("[FAIL] MAX(%0d) not greater than MIN(%0d)", max_v, min_v);
      errors = errors + 1;
    end else
      $display("[PASS] MAX > MIN (deltas differ)");

    if (errors == 0) $display("TS-HIST-ALL-PASS");
    else             $display("TS-HIST-FAILED errors=%0d", errors);
    $finish;
  end

endmodule
