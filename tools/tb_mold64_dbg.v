// tb_mold64_dbg: watchdog wrapper used only to locate an FSM stall.
// Drives the same stimulus as tb_mold64_reasm but dumps DUT state
// periodically and finishes on a bounded timeout instead of hanging.
`timescale 1ns / 1ps

module tb_mold64_dbg;

  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;

  reg  [4:0]  s_axi_awaddr = 0;
  reg         s_axi_awvalid = 0;
  wire        s_axi_awready;
  reg  [31:0] s_axi_wdata = 0;
  reg         s_axi_wvalid = 0;
  wire        s_axi_wready;
  wire [1:0]  s_axi_bresp;
  wire        s_axi_bvalid;
  reg         s_axi_bready = 1;
  reg  [4:0]  s_axi_araddr = 0;
  reg         s_axi_arvalid = 0;
  wire        s_axi_arready;
  wire [31:0] s_axi_rdata;
  wire [1:0]  s_axi_rresp;
  wire        s_axi_rvalid;
  reg         s_axi_rready = 1;

  reg  [63:0] s_axis_tdata = 0;
  reg  [7:0]  s_axis_tkeep = 8'hFF;
  reg         s_axis_tvalid = 0;
  wire        s_axis_tready;
  reg         s_axis_tlast = 0;

  wire [7:0]  m_axis_tdata;
  wire        m_axis_tvalid;
  reg         m_axis_tready = 1;

  mold64_reasm #(.SESSION(64'h4E41534441513031)) dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(s_axi_awaddr), .s_axi_awvalid(s_axi_awvalid),
    .s_axi_awready(s_axi_awready), .s_axi_wdata(s_axi_wdata),
    .s_axi_wstrb(4'hF), .s_axi_wvalid(s_axi_wvalid),
    .s_axi_wready(s_axi_wready), .s_axi_bresp(s_axi_bresp),
    .s_axi_bvalid(s_axi_bvalid), .s_axi_bready(s_axi_bready),
    .s_axi_araddr(s_axi_araddr), .s_axi_arvalid(s_axi_arvalid),
    .s_axi_arready(s_axi_arready), .s_axi_rdata(s_axi_rdata),
    .s_axi_rresp(s_axi_rresp), .s_axi_rvalid(s_axi_rvalid),
    .s_axi_rready(s_axi_rready),
    .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(s_axis_tkeep),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tlast(s_axis_tlast),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready)
  );

  integer k;
  integer i;

  // Write one 32-bit AXI4-Lite register.
  task axi_write(input [4:0] a, input [31:0] d);
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

  // Send n bytes from a byte array as 64-bit beats.
  task s_send_n(input integer n);
    begin
      i = 0;
      while (i < n) begin
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= 64'h0101010101010101;
        s_axis_tkeep  <= 8'hFF;
        s_axis_tlast  <= ((i + 8) >= n);
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        i = i + 8;
      end
      @(negedge aclk);
      s_axis_tvalid <= 0;
      s_axis_tlast  <= 0;
    end
  endtask

  initial begin
    // Watchdog: dump state, then stop.
    begin : wd
      for (k = 0; k < 24; k = k + 1) begin
        repeat (200) @(negedge aclk);
        $display("DBG t=%0t st=%0d rd=%0d wr=%0d bin=%0d ne=%b bv=%b mv=%b en=%b",
                 $time, dut.state, dut.pkt_rd_ptr, dut.pkt_wr_ptr,
                 dut.bytes_in, dut.fifo_not_empty, dut.byte_valid_r,
                 m_axis_tvalid, dut.enable);
      end
      $display("DBG-TIMEOUT");
      $finish;
    end
  end

  initial begin
    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);

    axi_write(5'h18, 32'h1);   // enable
    repeat (4) @(negedge aclk);

    $display("DBG-SEND start");
    s_send_n(128);
    $display("DBG-SEND done");
    repeat (400) @(negedge aclk);
    $display("DBG rx_packets=%0d rx_messages=%0d errors=%0d",
             dut.rx_packets, dut.rx_messages, dut.error_count);
    $finish;
  end

endmodule
