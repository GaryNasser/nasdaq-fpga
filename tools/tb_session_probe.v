// tb_session_probe: measures the session comparator in isolation.
//
// Sends exactly one well-formed MoldUDP64 packet with session "NASDAQ01"
// and records, for each of the 8 session bytes, what the DUT captured in
// session_mis[] and what session_mismatch evaluated to.
`timescale 1ns / 1ps

module tb_session_probe;

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

  integer i;
  integer budget;

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

  // One 50-byte packet: session(8) seq(2) count(2) len(2) body(36)
  reg [7:0] pkt [0:49];
  task send_pkt;
    begin
      i = 0;
      while (i < 50) begin
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= {pkt[i+7], pkt[i+6], pkt[i+5], pkt[i+4],
                          pkt[i+3], pkt[i+2], pkt[i+1], pkt[i]};
        s_axis_tkeep  <= 8'hFF;
        s_axis_tlast  <= ((i + 8) >= 50);
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
    // ---- build the packet ----
    pkt[0]=8'h4E; pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
    pkt[4]=8'h41; pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
    pkt[8]=8'h00; pkt[9]=8'h01;      // seq = 1
    pkt[10]=8'h00; pkt[11]=8'h01;    // count = 1
    pkt[12]=8'h00; pkt[13]=8'h24;    // len = 36
    for (i = 0; i < 36; i = i + 1)
      pkt[14+i] = (i == 0) ? 8'h41 : (8'h00 | i[7:0]);

    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);

    // Watch session_mis / session_mismatch settle.
    for (budget = 0; budget < 60; budget = budget + 1) begin
      repeat (60) @(negedge aclk);
      $display("PROBE t=%0t st=%0d mis=%b mismatch=%b sr0=%h sr7=%h err=%0d",
               $time, dut.state, dut.session_mis, dut.session_mismatch,
               dut.session_sr[0], dut.session_sr[7], dut.error_count);
      if (dut.error_count != 0) begin
        $display("PROBE-ERR-DETECTED");
        budget = 999;
      end
    end

    axi_write(5'h18, 32'h1);   // enable
    repeat (4) @(negedge aclk);
    $display("PROBE-SEND");
    fork
      send_pkt;
    join

    for (budget = 0; budget < 40; budget = budget + 1) begin
      repeat (40) @(negedge aclk);
      $display("PROBE2 t=%0t st=%0d mis=%b mm=%b sr0=%h sr1=%h err=%0d pkt=%0d msg=%0d",
               $time, dut.state, dut.session_mis, dut.session_mismatch,
               dut.session_sr[0], dut.session_sr[1], dut.error_count,
               dut.rx_packets, dut.rx_messages);
      if (dut.rx_messages != 0) begin
        $display("PROBE-GOT-MESSAGE");
        budget = 999;
      end
    end
    $display("PROBE-DONE");
    $finish;
  end

endmodule
