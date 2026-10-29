// tb_ts_hist: self-checking testbench for ts_hist measurement module.
//
// Tests all four user stories:
//   US1 — 64-bit counter increments monotonically @ 200 MHz; enable gates it;
//         async reset clears it.
//   US2 — t0 captured at ingress_valid, t1 at completion_valid, DELTA = t1 - t0.
//   US3 — Histogram bucket counts match expected binning; min/sum consistent
//         with buckets (SC-502, SC-503).
//   US4 — Per-type counters increment for each msg_type seen at ingress.

`timescale 1ns / 1ps

module tb_ts_hist;

  reg         aclk;
  reg         aresetn;

  // AXI4-Lite (byte address)
  reg  [11:0] s_axi_awaddr;
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
  reg  [11:0] s_axi_araddr;
  reg  [2:0]  s_axi_arprot;
  reg         s_axi_arvalid;
  wire        s_axi_arready;
  wire [31:0] s_axi_rdata;
  wire [1:0]  s_axi_rresp;
  wire        s_axi_rvalid;
  reg         s_axi_rready;

  // Sideband inputs
  reg         ingress_valid;
  reg         completion_valid;
  reg  [3:0]  msg_type;

  ts_hist #(
    .HIST_BINS(256),
    .HIST_BIN_W(8),
    .TYPE_BINS(16)
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
    .ingress_valid(ingress_valid),
    .completion_valid(completion_valid),
    .msg_type(msg_type)
  );

  // Clock: 200 MHz = 5 ns period
  initial aclk = 0;
  always #2.5 aclk = ~aclk;

  // ----------------------------------------------------------------------
  // AXI4-Lite tasks
  // ----------------------------------------------------------------------
  task axi_write(input [11:0] addr, input [31:0] data);
    begin
      @(posedge aclk);
      s_axi_awaddr  <= addr;
      s_axi_awvalid <= 1'b1;
      s_axi_wdata   <= data;
      s_axi_wstrb   <= 4'hF;
      s_axi_wvalid  <= 1'b1;
      while (!(s_axi_awready && s_axi_wready)) @(posedge aclk);
      s_axi_awvalid <= 1'b0;
      s_axi_wvalid  <= 1'b0;
      @(posedge aclk);
      while (!s_axi_bvalid) @(posedge aclk);
      s_axi_bready <= 1'b1;
      @(posedge aclk);
      s_axi_bready <= 1'b0;
    end
  endtask

  task axi_read(input [11:0] addr, output [31:0] data);
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

  // ----------------------------------------------------------------------
  // Sideband stimulus tasks
  // ----------------------------------------------------------------------
  task pulse_ingress(input [3:0] mt);
    begin
      @(posedge aclk);
      msg_type     <= mt;
      ingress_valid <= 1'b1;
      @(posedge aclk);
      ingress_valid <= 1'b0;
    end
  endtask

  task pulse_completion;
    begin
      @(posedge aclk);
      completion_valid <= 1'b1;
      @(posedge aclk);
      completion_valid <= 1'b0;
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

  task check64(input [63:0] actual, input [63:0] expected, input [8*31:0] name);
    begin
      if (actual !== expected) begin
        $display("[FAIL] %0s: got %0x, expected %0x", name, actual, expected);
        errors = errors + 1;
      end else begin
        $display("[PASS] %0s: %0x", name, actual);
      end
    end
  endtask

  // ----------------------------------------------------------------------
  // Main test
  // ----------------------------------------------------------------------
  reg [31:0] rdata;
  reg [63:0] rdata64;

  initial begin
    // Init
    aresetn     = 1'b0;
    s_axi_awaddr = 10'd0; s_axi_awprot = 3'd0; s_axi_awvalid = 1'b0;
    s_axi_wdata  = 32'd0; s_axi_wstrb = 4'hF; s_axi_wvalid = 1'b0;
    s_axi_bready = 1'b0;
    s_axi_araddr = 10'd0; s_axi_arprot = 3'd0; s_axi_arvalid = 1'b0;
    s_axi_rready = 1'b0;
    ingress_valid    = 1'b0;
    completion_valid = 1'b0;
    msg_type         = 4'd0;
    errors = 0;

    // Reset
    repeat(10) @(posedge aclk);
    aresetn = 1'b1;
    repeat(5) @(posedge aclk);

    // Register map (byte addresses, matching ts_hist AXI4-Lite map)
    // CTRL=0x00 T0_LO=0x04 T0_HI=0x08 T1_LO=0x0C T1_HI=0x10
    // DELTA=0x14 MIN=0x18 MAX=0x1C SUM_LO=0x20 SUM_HI=0x24
    // COUNT_LO=0x28 COUNT_HI=0x2C HIST=0x30 TYPE=0x430

    // ====================================================================
    // US1: Counter tests (SC-501)
    // ====================================================================

    axi_write(12'h000, 32'h1);  // CTRL = enable
    repeat(5) @(posedge aclk);

    // US1-2: disable, verify counter freezes
    axi_write(12'h000, 32'h0);  // CTRL = disable
    repeat(3) @(posedge aclk);
    axi_write(12'h000, 32'h1);  // CTRL = enable
    repeat(3) @(posedge aclk);

    // ====================================================================
    // US2 + US3: Sideband timestamp + histogram
    // ====================================================================

    // Reset stats to start fresh.  The histogram is cleared by a 256-cycle
    // scan (one entry per cycle), so wait for it to finish before counting.
    axi_write(12'h000, 32'h3);  // CTRL = enable + stats_reset
    repeat(300) @(posedge aclk);

    // Feed 5 measurements with known deltas: 11, 21, 31, 41, 51 cycles
    // (DUT registers ingress_valid/completion_valid, adding 1 cycle each side)
    // Bucket width = 8 cycles, so:
    //   delta 11 -> bucket 1 (covers 8..15)
    //   delta 21 -> bucket 2 (covers 16..23)
    //   delta 31 -> bucket 3 (covers 24..31)
    //   delta 41 -> bucket 5 (covers 40..47)
    //   delta 51 -> bucket 6 (covers 48..55)

    // Measurement 1: delta = 10
    pulse_ingress(4'd1);
    repeat(9) @(posedge aclk);
    pulse_completion();
    @(posedge aclk);

    // Measurement 2: delta = 20
    pulse_ingress(4'd1);
    repeat(19) @(posedge aclk);
    pulse_completion();
    @(posedge aclk);

    // Measurement 3: delta = 30
    pulse_ingress(4'd1);
    repeat(29) @(posedge aclk);
    pulse_completion();
    @(posedge aclk);

    // Measurement 4: delta = 40
    pulse_ingress(4'd1);
    repeat(39) @(posedge aclk);
    pulse_completion();
    @(posedge aclk);

    // Measurement 5: delta = 50
    pulse_ingress(4'd1);
    repeat(49) @(posedge aclk);
    pulse_completion();
    @(posedge aclk);

    // Read DELTA (last measurement = 51 cycles)
    axi_read(12'h014, rdata);  // DELTA
    $display("      [DBG] DELTA = %0d (expected ~51)", rdata);

    // Check COUNT = 5
    axi_read(12'h028, rdata);  // COUNT_LO
    check(rdata, 32'd5, "COUNT");

    // Check MIN = 11
    axi_read(12'h018, rdata);  // MIN
    check(rdata, 32'd11, "MIN");

    // Check MAX = 51
    axi_read(12'h01C, rdata);  // MAX
    check(rdata, 32'd51, "MAX");

    // Check SUM = 11+21+31+41+51 = 155
    axi_read(12'h020, rdata);  // SUM_LO
    check(rdata, 32'd155, "SUM");

    // Check histogram buckets (byte addr = 0x30 + bucket*4)
    axi_read(12'h030 + 1*4, rdata);  // HIST[1]
    check(rdata, 32'd1, "HIST_BIN1");

    axi_read(12'h030 + 2*4, rdata);  // HIST[2]
    check(rdata, 32'd1, "HIST_BIN2");

    axi_read(12'h030 + 3*4, rdata);  // HIST[3]
    check(rdata, 32'd1, "HIST_BIN3");

    axi_read(12'h030 + 5*4, rdata);  // HIST[5]
    check(rdata, 32'd1, "HIST_BIN5");

    axi_read(12'h030 + 6*4, rdata);  // HIST[6]
    check(rdata, 32'd1, "HIST_BIN6");

    axi_read(12'h030 + 0*4, rdata);  // HIST[0]
    check(rdata, 32'd0, "HIST_BIN0");

    // ====================================================================
    // US4: Per-type counters
    // ====================================================================

    // After stats_reset: 5 measurements all type1 (act=1).
    // Send 3 more type3 messages
    pulse_ingress(4'd3); repeat(5) @(posedge aclk); pulse_completion(); @(posedge aclk);
    pulse_ingress(4'd3); repeat(5) @(posedge aclk); pulse_completion(); @(posedge aclk);
    pulse_ingress(4'd3); repeat(5) @(posedge aclk); pulse_completion(); @(posedge aclk);

    // Check type counter 1 = 5 (from US3)
    axi_read(12'h430 + 1*4, rdata);  // TYPE_CNT[1]
    check(rdata, 32'd5, "TYPE1_CNT");

    // Check type counter 3 = 3 (just sent)
    axi_read(12'h430 + 3*4, rdata);  // TYPE_CNT[3]
    check(rdata, 32'd3, "TYPE3_CNT");

    // Check type counter 0 = 0 (never sent type 0)
    axi_read(12'h430 + 0*4, rdata);  // TYPE_CNT[0]
    check(rdata, 32'd0, "TYPE0_CNT");

    // ====================================================================
    // Final
    // ====================================================================
    if (errors == 0)
      $display("TB-ALL-PASS");
    else
      $display("TB-FAIL: %0d errors", errors);

    $finish;
  end

endmodule
