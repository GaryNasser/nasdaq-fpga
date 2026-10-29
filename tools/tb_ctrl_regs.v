// tb_ctrl_regs: self-checking testbench for ctrl_regs.
//
// Checks (from data-model.md invariants):
//   1. after reset CTRL==0 and COUNT==0
//   2. COUNT frozen while CTRL[0]==0
//   3. COUNT strictly increases while CTRL[0]==1
//   4. COUNT frozen again after CTRL[0] cleared
//   5. bus write to COUNT is ignored
//   6. reserved bits of CTRL discard writes and read back 0
//   7. CTRL write with WSTRB[0]==0 (byte-0 not strobed) is ignored

`timescale 1ns / 1ps

module tb_ctrl_regs;

  reg         aclk = 0;
  reg         aresetn = 0;
  reg  [3:0]  awaddr = 0;
  reg  [2:0]  awprot = 0;
  reg         awvalid = 0;
  wire        awready;
  reg  [31:0] wdata = 0;
  reg  [3:0]  wstrb = 4'b1111;
  reg         wvalid = 0;
  wire        wready;
  wire [1:0]  bresp;
  wire        bvalid;
  reg         bready = 1;    // always ready to take B
  reg  [3:0]  araddr = 0;
  reg  [2:0]  arprot = 0;
  reg         arvalid = 0;
  wire        arready;
  wire [31:0] rdata;
  wire [1:0]  rresp;
  wire        rvalid;
  reg         rready = 1;    // always ready to take R

  ctrl_regs dut (
    .S_AXI_ACLK(aclk), .S_AXI_ARESETN(aresetn),
    .S_AXI_AWADDR(awaddr), .S_AXI_AWPROT(awprot),
    .S_AXI_AWVALID(awvalid), .S_AXI_AWREADY(awready),
    .S_AXI_WDATA(wdata), .S_AXI_WSTRB(wstrb),
    .S_AXI_WVALID(wvalid), .S_AXI_WREADY(wready),
    .S_AXI_BRESP(bresp), .S_AXI_BVALID(bvalid), .S_AXI_BREADY(bready),
    .S_AXI_ARADDR(araddr), .S_AXI_ARPROT(arprot),
    .S_AXI_ARVALID(arvalid), .S_AXI_ARREADY(arready),
    .S_AXI_RDATA(rdata), .S_AXI_RRESP(rresp),
    .S_AXI_RVALID(rvalid), .S_AXI_RREADY(rready)
  );

  always #5 aclk = ~aclk;    // 100 MHz in sim (function, not timing, test)

  integer errors = 0;

  task check(input cond, input [255:0] name);
    begin
      if (cond) $display("[PASS] %0s", name);
      else begin $display("[FAIL] %0s", name); errors = errors + 1; end
    end
  endtask

  // Write with level-polled handshake (BREADY is tied high, so the B
  // beat self-completes; repeated fires are idempotent - same data).
  task axi_write(input [3:0] addr, input [31:0] data);
    begin
      @(negedge aclk);
      awaddr <= addr; awvalid <= 1;
      wdata  <= data; wvalid  <= 1;
      repeat (3) @(negedge aclk);   // ensure at least one AW/W fire
      awvalid <= 0; wvalid <= 0;
      while (bvalid) @(negedge aclk); // drain pending B beat
      @(negedge aclk);
    end
  endtask

  // Write variant with explicit byte strobes (WSTRB != 1111 coverage).
  task axi_write_strb(input [3:0] addr, input [31:0] data, input [3:0] strb);
    begin
      @(negedge aclk);
      awaddr <= addr; awvalid <= 1;
      wdata  <= data; wstrb  <= strb; wvalid  <= 1;
      repeat (3) @(negedge aclk);
      awvalid <= 0; wvalid <= 0;
      while (bvalid) @(negedge aclk);
      @(negedge aclk);
      wstrb <= 4'b1111;
    end
  endtask

  // Read with level-polled handshake (RREADY is tied high).
  task axi_read(input [3:0] addr, output [31:0] data);
    begin
      @(negedge aclk);
      araddr <= addr; arvalid <= 1;
      @(negedge aclk);
      while (!rvalid) @(negedge aclk);
      data = rdata;
      arvalid <= 0;
      @(negedge aclk);
    end
  endtask

  reg [31:0] v0, v1, v2;

  initial begin
    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);

    // 1. reset values
    axi_read(4'h0, v0);
    check(v0 == 32'h0, "CTRL reads 0 after reset");
    axi_read(4'h4, v0);
    check(v0 == 32'h0, "COUNT reads 0 after reset");

    // 2. frozen while disabled
    repeat (10) @(negedge aclk);
    axi_read(4'h4, v1);
    check(v1 == v0, "COUNT frozen while disabled");

    // 3. enable -> strictly increasing
    axi_write(4'h0, 32'h1);
    repeat (10) @(negedge aclk);
    axi_read(4'h4, v1);
    check(v1 > v0, "COUNT increases when enabled");
    repeat (10) @(negedge aclk);
    axi_read(4'h4, v2);
    check(v2 > v1, "COUNT keeps increasing");

    // 4. disable -> frozen (two reads after disable must be equal)
    axi_write(4'h0, 32'h0);
    repeat (10) @(negedge aclk);
    axi_read(4'h4, v0);
    repeat (10) @(negedge aclk);
    axi_read(4'h4, v1);
    check(v1 == v0, "COUNT frozen after disable");

    // 5. bus write to COUNT is ignored
    axi_write(4'h4, 32'hDEADBEEF);
    repeat (4) @(negedge aclk);
    axi_read(4'h4, v1);
    check(v1 == v0, "bus write to COUNT ignored");

    // 6. CTRL reserved bits discard
    axi_write(4'h0, 32'hFFFFFFFE);   // all reserved bits set, enable=0
    repeat (4) @(negedge aclk);
    axi_read(4'h0, v1);
    check(v1 == 32'h0, "CTRL reserved bits read 0");
    axi_write(4'h0, 32'hFFFFFFFF);   // reserved + enable
    axi_read(4'h0, v1);
    check(v1 == 32'h1, "CTRL keeps only bit0");

    // 7. CTRL write with WSTRB[0]==0 must not change CTRL (byte-0 strobe)
    axi_write(4'h0, 32'h0);          // disable
    repeat (4) @(negedge aclk);
    axi_write_strb(4'h0, 32'h1, 4'b1110);   // bytes 1..3 strobed, byte 0 not
    repeat (4) @(negedge aclk);
    axi_read(4'h0, v1);
    check(v1 == 32'h0, "CTRL write with WSTRB[0]=0 ignored");
    axi_write(4'h0, 32'h1);          // full strobe still works
    axi_read(4'h0, v1);
    check(v1 == 32'h1, "CTRL write with WSTRB[0]=1 takes effect");

    if (errors == 0) begin
      $display("TB-ALL-PASS");
      $finish;
    end else begin
      $display("TB-FAILED %0d error(s)", errors);
      $finish;
    end
  end

endmodule
