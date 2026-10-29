// ctrl_regs: minimal AXI4-Lite register slave for overlay bootstrap.
//
// Register map (frozen by specs/001-overlay-bootstrap/contracts):
//   0x00 CTRL  RW  bit0 counter enable; [31:1] reserved (write 0, read 0)
//   0x04 COUNT RO  free-running counter, +COUNTER_STEP per clock while
//                  enabled; cleared by reset; bus writes are ignored
//
// Seed of replan.md module #8 (ctrl_regs production version): offsets
// 0x00/0x04 are frozen; future extensions only append new offsets.

`timescale 1ns / 1ps

module ctrl_regs #(
    parameter [31:0] COUNTER_STEP = 32'd1
) (
    input  wire        S_AXI_ACLK,
    input  wire        S_AXI_ARESETN,

    // AXI4-Lite write channel
    input  wire [3:0]  S_AXI_AWADDR,
    input  wire [2:0]  S_AXI_AWPROT,
    input  wire        S_AXI_AWVALID,
    output wire        S_AXI_AWREADY,
    input  wire [31:0] S_AXI_WDATA,
    input  wire [3:0]  S_AXI_WSTRB,
    input  wire        S_AXI_WVALID,
    output wire        S_AXI_WREADY,
    output wire [1:0]  S_AXI_BRESP,
    output wire        S_AXI_BVALID,
    input  wire        S_AXI_BREADY,

    // AXI4-Lite read channel
    input  wire [3:0]  S_AXI_ARADDR,
    input  wire [2:0]  S_AXI_ARPROT,
    input  wire        S_AXI_ARVALID,
    output wire        S_AXI_ARREADY,
    output wire [31:0] S_AXI_RDATA,
    output wire [1:0]  S_AXI_RRESP,
    output wire        S_AXI_RVALID,
    input  wire        S_AXI_RREADY
);

  // Address decode: byte offset bit [2] selects the register
  localparam ADDR_CTRL  = 1'b0;
  localparam ADDR_COUNT = 1'b1;

  reg        ctrl_en;
  reg [31:0] count;

  reg        b_valid;
  reg        r_valid;
  reg [31:0] r_data;

  // ---- write channel --------------------------------------------------
  // Accept a write only when both AW and W are valid and no B beat is
  // pending (legal AXI-Lite: next write waits for B handshake).
  wire wr_fire = S_AXI_AWVALID && S_AXI_WVALID && !b_valid;

  assign S_AXI_AWREADY = wr_fire;
  assign S_AXI_WREADY  = wr_fire;

  always @(posedge S_AXI_ACLK) begin
    if (!S_AXI_ARESETN) begin
      b_valid <= 1'b0;
      ctrl_en <= 1'b0;
    end else begin
      if (wr_fire) begin
        b_valid <= 1'b1;
        if (S_AXI_AWADDR[2] == ADDR_CTRL && S_AXI_WSTRB[0])
          ctrl_en <= S_AXI_WDATA[0];   // byte-0 strobe; reserved bits discarded
        // writes to COUNT (ADDR_COUNT) are ignored by design
      end else if (S_AXI_BVALID && S_AXI_BREADY) begin
        b_valid <= 1'b0;
      end
    end
  end

  assign S_AXI_BVALID = b_valid;
  assign S_AXI_BRESP  = 2'b00;         // OKAY

  // ---- read channel ---------------------------------------------------
  wire rd_fire = S_AXI_ARVALID && !r_valid;

  assign S_AXI_ARREADY = rd_fire;

  always @(posedge S_AXI_ACLK) begin
    if (!S_AXI_ARESETN) begin
      r_valid <= 1'b0;
      r_data  <= 32'd0;
    end else begin
      if (rd_fire) begin
        r_valid <= 1'b1;
        r_data  <= (S_AXI_ARADDR[2] == ADDR_CTRL) ? {31'b0, ctrl_en} : count;
      end else if (S_AXI_RVALID && S_AXI_RREADY) begin
        r_valid <= 1'b0;
      end
    end
  end

  assign S_AXI_RVALID = r_valid;
  assign S_AXI_RDATA  = r_data;
  assign S_AXI_RRESP  = 2'b00;         // OKAY

  // ---- free-running counter -------------------------------------------
  always @(posedge S_AXI_ACLK) begin
    if (!S_AXI_ARESETN)
      count <= 32'd0;
    else if (ctrl_en)
      count <= count + COUNTER_STEP;   // natural 32-bit wrap
  end

endmodule
