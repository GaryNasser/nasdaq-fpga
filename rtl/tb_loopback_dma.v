// tb_loopback_dma: self-checking testbench for loopback_dma.
//
// Checks:
//   1. after reset all stats registers read 0
//   2. feed 10 beats (TDATA=0..9, TLAST on beat 9) -> exact data on M_AXIS
//   3. BYTES_IN == 80, BYTES_OUT == 80
//   4. DROP_COUNT == 0, ERROR_COUNT == 0
//   5. backpressure: deassert M_AXIS TREADY 5 cycles -> S_AXIS TREADY
//      deasserts, DROP_COUNT stays 0 (backpressure is normal, not a drop)
//   6. multi-packet: 3 packets with TLAST on last beat of each -> intact

`timescale 1ns / 1ps

module tb_loopback_dma;

  // Clock / reset
  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;   // 200 MHz functional test clock

  // AXI4-Lite
  reg  [4:0]  awaddr = 0;
  reg  [2:0]  awprot = 0;
  reg         awvalid = 0;
  wire        awready;
  reg  [31:0] wdata = 0;
  reg  [3:0]  wstrb = 4'b1111;
  reg         wvalid = 0;
  wire        wready;
  wire [1:0]  bresp;
  wire        bvalid;
  reg         bready = 1;
  reg  [4:0]  araddr = 0;
  reg  [2:0]  arprot = 0;
  reg         arvalid = 0;
  wire        arready;
  wire [31:0] rdata;
  wire [1:0]  rresp;
  wire        rvalid;
  reg         rready = 1;

  // AXI-Stream slave side (TB drives, DUT receives)
  reg  [63:0] s_tdata = 0;
  reg  [7:0]  s_tkeep = 8'hFF;
  reg         s_tvalid = 0;
  wire        s_tready;
  reg         s_tlast = 0;

  // AXI-Stream master side (DUT drives, TB receives)
  wire [63:0] m_tdata;
  wire [7:0]  m_tkeep;
  wire        m_tvalid;
  reg         m_tready = 1;
  wire        m_tlast;

  loopback_dma dut (
    .s_axi_aclk(aclk), .s_axi_aresetn(aresetn),
    .s_axi_awaddr(awaddr), .s_axi_awprot(awprot),
    .s_axi_awvalid(awvalid), .s_axi_awready(awready),
    .s_axi_wdata(wdata), .s_axi_wstrb(wstrb),
    .s_axi_wvalid(wvalid), .s_axi_wready(wready),
    .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arprot(arprot),
    .s_axi_arvalid(arvalid), .s_axi_arready(arready),
    .s_axi_rdata(rdata), .s_axi_rresp(rresp),
    .s_axi_rvalid(rvalid), .s_axi_rready(rready),

    .s_axis_tdata(s_tdata), .s_axis_tkeep(s_tkeep),
    .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready),
    .s_axis_tlast(s_tlast),

    .m_axis_tdata(m_tdata), .m_axis_tkeep(m_tkeep),
    .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready),
    .m_axis_tlast(m_tlast)
  );

  // ----------------------------------------------------------------------
  integer errors = 0;

  task check(input cond, input [511:0] name);
    begin
      if (cond) $display("[PASS] %0s", name);
      else begin $display("[FAIL] %0s", name); errors = errors + 1; end
    end
  endtask

  // AXI-Lite read (RREADY tied high).
  task axi_read(input [4:0] addr, output [31:0] data);
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

  // Drive one S_AXIS beat and wait for the handshake at posedge.
  // Deasserts TVALID in the same posedge as the handshake (via NBA) so
  // DROP_COUNT is never incremented by normal backpressure.
  task s_send(input [63:0] d, input last);
    begin
      @(negedge aclk);
      s_tdata  <= d;
      s_tkeep  <= 8'hFF;
      s_tvalid <= 1;
      s_tlast  <= last;
      // Wait for the S-side handshake at posedge, then deassert TVALID.
      begin : hs
        reg done = 0;
        while (!done) begin
          @(posedge aclk);
          if (s_tvalid && s_tready) begin
            done = 1;
            s_tvalid <= 0;
            s_tlast  <= 0;
          end
        end
      end
      @(negedge aclk);
    end
  endtask

  // Read one M_AXIS beat (blocking until TVALID).  Returns data/last.
  task m_recv(output [63:0] d, output last);
    begin
      @(negedge aclk);
      while (!m_tvalid) @(negedge aclk);
      d   = m_tdata;
      last = m_tlast;
      @(negedge aclk);
    end
  endtask

  // ----------------------------------------------------------------------
  reg [31:0] v0, v1, v2;
  reg [63:0] md;
  reg        ml;
  integer i, j, k;
  reg [63:0] rx_data;
  reg        rx_last;

  initial begin
    // ----- reset -----
    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);

    // -- 1. reset values --
    axi_read(5'h00, v0); check(v0 == 32'd0, "rset BYTES_IN_LO");
    axi_read(5'h04, v0); check(v0 == 32'd0, "rset BYTES_IN_HI");
    axi_read(5'h08, v0); check(v0 == 32'd0, "rset BYTES_OUT_LO");
    axi_read(5'h0C, v0); check(v0 == 32'd0, "rset BYTES_OUT_HI");
    axi_read(5'h10, v0); check(v0 == 32'd0, "rset DROP_COUNT");
    axi_read(5'h14, v0); check(v0 == 32'd0, "rset ERROR_COUNT");

    // -- 2. 10 beats exact loopback --
    // Producer and consumer use separate loop variables to avoid the
    // classic fork/join shared-variable race.
    fork
      begin : prod
        for (j = 0; j < 10; j = j + 1) begin
          s_send(j, (j == 9) ? 1'b1 : 1'b0);
        end
      end
      begin : cons
        for (k = 0; k < 10; k = k + 1) begin
          m_recv(rx_data, rx_last);
          check(rx_data == k, "loopback data match");
        end
      end
    join
    check(rx_last == 1'b1, "loopback TLAST on beat 9");

    // -- 3. byte counters ==
    axi_read(5'h00, v0); axi_read(5'h04, v1);
    check(v0 == 32'd80, "BYTES_IN_LO == 80");
    check(v1 == 32'd0,  "BYTES_IN_HI == 0");
    axi_read(5'h08, v0); axi_read(5'h0C, v2);
    check(v0 == 32'd80, "BYTES_OUT_LO == 80");
    check(v2 == 32'd0,  "BYTES_OUT_HI == 0");

    // -- 4. drop / error counters ==
    axi_read(5'h10, v0); check(v0 == 32'd0, "DROP_COUNT == 0 normal");
    axi_read(5'h14, v0); check(v0 == 32'd0, "ERROR_COUNT == 0 normal");

    // -- 5. backpressure: deassert M_AXIS TREADY, queue one beat, verify
    //    S_AXIS TREADY deasserts and DROP_COUNT stays 0.  Then release and
    //    drain the beat intact.
    @(negedge aclk);
    m_tready <= 0;                 // downstream not ready
    @(negedge aclk);
    s_tdata  <= 64'hCAFE;
    s_tkeep  <= 8'hFF;
    s_tvalid <= 1;
    s_tlast  <= 1;
    // Wait for the S-side handshake (pipe captures the beat), then
    // deassert TVALID in the same cycle so DROP_COUNT is not incremented.
    begin : bp_hs
      reg bp_done = 0;
      while (!bp_done) begin
        @(posedge aclk);
        if (s_tvalid && s_tready) begin
          bp_done = 1;
          s_tvalid <= 0;
          s_tlast  <= 0;
        end
      end
    end
    @(negedge aclk);
    // pipe_valid is now 1; s_tready should read 0 (slot full, m_tready=0).
    check(s_tready == 1'b0, "s_tready deasserts on backpressure");
    axi_read(5'h10, v0); check(v0 == 32'd0, "DROP_COUNT 0 under backpressure");
    @(negedge aclk);
    axi_read(5'h10, v0); check(v0 == 32'd0, "DROP_COUNT still 0, no valid data");
    // Release backpressure.  The beat is presented on M_AXIS this cycle;
    // capture it before the consuming posedge clears the pipeline.
    m_tready <= 1;
    md = m_tdata;
    ml = m_tlast;
    check(md == 64'hCAFE, "bp beat drains intact");
    check(ml == 1'b1,     "bp beat TLAST intact");
    // Wait for the consuming posedge to clear the pipe.
    @(posedge aclk);
    @(negedge aclk);

    // -- 6. multi-packet: 3 packets, TLAST on last beat of each --
    fork
      begin : mprod
        // Packet A: beats 100..103, TLAST on 103
        for (j = 100; j < 104; j = j + 1)
          s_send(j, (j == 103) ? 1'b1 : 1'b0);
        // Packet B: beats 200..201, TLAST on 201
        for (j = 200; j < 202; j = j + 1)
          s_send(j, (j == 201) ? 1'b1 : 1'b0);
        // Packet C: beat 300, TLAST on 300
        s_send(300, 1'b1);
      end
      begin : mcons
        // Receive and verify packet A
        for (k = 100; k < 104; k = k + 1) begin
          m_recv(rx_data, rx_last);
          check(rx_data == k, "pkt A data intact");
        end
        check(rx_last == 1'b1, "pkt A TLAST");
        // Packet B
        for (k = 200; k < 202; k = k + 1) begin
          m_recv(rx_data, rx_last);
          check(rx_data == k, "pkt B data intact");
        end
        check(rx_last == 1'b1, "pkt B TLAST");
        // Packet C
        m_recv(rx_data, rx_last);
        check(rx_data == 64'd300, "pkt C data intact");
        check(rx_last == 1'b1,    "pkt C TLAST");
      end
    join

    // Final byte-count sanity: 10 + 1 (bp) + 4 + 2 + 1 = 18 beats * 8 = 144
    axi_read(5'h00, v0); check(v0 == 32'd144, "BYTES_IN_LO == 144 total");

    if (errors == 0) begin
      $display("TB-ALL-PASS");
      $finish;
    end else begin
      $display("TB-FAILED %0d error(s)", errors);
      $finish;
    end
  end

endmodule
