// tb_rate: measure the reader's and writer's sustained byte rates.
//
// The previous rounds showed that changing the TREADY threshold, the reserve
// and the occupancy source all left the 89-packet failure bit-for-bit
// identical, which means flow control is not the limiter. The trace also showed
// the reader at byte 25 while 324 had arrived.
//
// byte_valid_r requires rd_valid_d == 3, i.e. the reader waits three cycles per
// word and can therefore consume at most one byte every three cycles, while the
// writer takes up to 8 bytes per beat. This measures both rates directly and
// reports the ratio, which decides whether the FIFO can ever keep up.
`timescale 1ns / 1ps

module tb_rate;

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

  integer i, k, npkt, ef, b;
  reg mon_on;
  parameter NPKT      = 89;
  parameter MSG_LEN   = 36;
  parameter PKT_BYTES = 50;

  reg [7:0] pktbuf [0:PKT_BYTES-1];

  // ---- rate counters -----------------------------------------------------
  integer cyc;           // total cycles after enable
  integer wr_bytes;      // bytes accepted
  integer rd_bytes;      // bytes consumed (rd advances)
  integer wr_stall;      // cycles with tvalid && !tready
  integer rd_wait;       // cycles with data available but reader idle
  reg [11:0] rd_last;
  integer sample;

  initial begin
    cyc = 0; wr_bytes = 0; rd_bytes = 0; wr_stall = 0; rd_wait = 0;
    rd_last = 12'd0; sample = 0;
  end

  always @(posedge aclk) begin
    if (aresetn && mon_on) begin
      cyc = cyc + 1;
      if (s_axis_tvalid && !s_axis_tready) wr_stall = wr_stall + 1;
      if (dut.pkt_rd_ptr != rd_last) begin
        rd_bytes = rd_bytes + 1;
        rd_last <= dut.pkt_rd_ptr;
      end
      // Report every 500 cycles while the run is in flight.
      if (cyc % 500 == 0) begin
        $display("RATE cyc=%0d acc=%0d rd=%0d gap=%0d stall=%0d",
                 cyc, dut.bytes_accepted, rd_bytes,
                 dut.bytes_accepted - rd_bytes, wr_stall);
      end
    end
  end


  task axi_write(input [4:0] a, input [31:0] v);
    begin
      @(negedge aclk);
      s_axi_awaddr <= a; s_axi_awvalid <= 1;
      s_axi_wdata  <= v; s_axi_wvalid  <= 1;
      while (!(s_axi_awready && s_axi_wready)) @(negedge aclk);
      @(negedge aclk);
      s_axi_awvalid <= 0; s_axi_wvalid <= 0;
      while (!s_axi_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  task build_pkt(input [15:0] sq);
    begin
      pktbuf[0]=8'h4E; pktbuf[1]=8'h41; pktbuf[2]=8'h53; pktbuf[3]=8'h44;
      pktbuf[4]=8'h41; pktbuf[5]=8'h51; pktbuf[6]=8'h30; pktbuf[7]=8'h31;
      pktbuf[8]=sq[15:8]; pktbuf[9]=sq[7:0];
      pktbuf[10]=8'h00; pktbuf[11]=8'h01;
      pktbuf[12]=8'h00; pktbuf[13]=MSG_LEN[7:0];
      for (k = 0; k < MSG_LEN; k = k + 1)
        pktbuf[14+k] = (k == 0) ? 8'h41 : (8'h00 | k[7:0]);
    end
  endtask

  task send_built;
    reg [63:0] w;
    begin
      b = 0;
      while (b < PKT_BYTES) begin
        for (k = 0; k < 8; k = k + 1)
          w[k*8 +: 8] = ((b + k) < PKT_BYTES) ? pktbuf[b + k] : 8'h00;
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= w;
        if ((b + 8) > PKT_BYTES) begin
          s_axis_tkeep <= (8'hFF >> (8 - (PKT_BYTES - b)));
          s_axis_tlast <= 1'b1;
        end else begin
          s_axis_tkeep <= 8'hFF;
          s_axis_tlast <= ((b + 8) == PKT_BYTES);
        end
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        b = b + ((b + 8 > PKT_BYTES) ? (PKT_BYTES - b) : 8);
      end
      @(negedge aclk);
      s_axis_tvalid <= 0;
      s_axis_tlast  <= 0;
    end
  endtask

  initial begin
    mon_on = 0;
    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);
    mon_on = 1;

    for (npkt = 0; npkt < NPKT; npkt = npkt + 1) begin
      build_pkt(npkt + 1);
      send_built;
    end
    repeat (400000) @(negedge aclk);

    $display("RATE-TOTAL cyc=%0d acc=%0d rd=%0d wr_stall=%0d",
             cyc, dut.bytes_accepted, rd_bytes, wr_stall);
    $display("RATE-RATIO writer=%.3f B/cyc reader=%.3f B/cyc",
             wr_bytes*1.0/cyc, rd_bytes*1.0/cyc);
    $display("RESULT rx_packets=%0d errs=%0d", dut.rx_packets, dut.error_count);
    $finish;
  end

endmodule
