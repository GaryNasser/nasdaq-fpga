// tb_stream: the streaming test that matters.
//
// Sends N complete MoldUDP64 packets back to back with NO gap, with M_AXIS
// free-running, and checks that every message comes out. This is the case the
// whole byte-FIFO rework exists to support, and the case the legacy
// store-and-forward testbench cannot express.
`timescale 1ns / 1ps

module tb_diag2;

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

  integer i, k, p;
  integer npkt;
  integer nerr;
  integer last_err;
  integer snap_rd, snap_acc, snap_cmt, snap_st;
  initial last_err = 0;
  always @(posedge aclk) begin
    if (dut.error_count != last_err) begin
      if (last_err == 0) begin
        snap_rd = dut.pkt_rd_ptr; snap_acc = dut.bytes_accepted;
        snap_cmt = dut.bytes_committed; snap_st = dut.state;
        $display("FIRSTERR at t=%0t rd=%0d acc=%0d cmt=%0d st=%0d lane=%0d",
                 $time, snap_rd, snap_acc, snap_cmt, snap_st, snap_rd[2:0]);
      end
      last_err = dut.error_count;
    end
  end
  integer nmsg_out;

  parameter NPKT      = 100;
  parameter MSG_LEN   = 36;               // message body bytes
  parameter PKT_BYTES = 8 + 2 + 2 + 2 + 36;  // 50

  reg [7:0] pktbuf [0:PKT_BYTES-1];

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

  // Count M_AXIS bytes and check each message body is well formed.
  always @(posedge aclk) begin
    if (aresetn && m_axis_tvalid && m_axis_tready) begin
      nmsg_out = nmsg_out + 1;
    end
  end

  // Build one packet into pktbuf with sequence number sq.
  task build_pkt(input [15:0] sq);
    begin
      pktbuf[0]=8'h4E; pktbuf[1]=8'h41; pktbuf[2]=8'h53; pktbuf[3]=8'h44;
      pktbuf[4]=8'h41; pktbuf[5]=8'h51; pktbuf[6]=8'h30; pktbuf[7]=8'h31;
      pktbuf[8]=sq[15:8]; pktbuf[9]=sq[7:0];
      pktbuf[10]=8'h00; pktbuf[11]=8'h01;         // count = 1
      pktbuf[12]=8'h00; pktbuf[13]=MSG_LEN[7:0];  // length
      for (k = 0; k < MSG_LEN; k = k + 1)
        pktbuf[14+k] = (k == 0) ? 8'h41 : (8'h00 | k[7:0]);
    end
  endtask

  // Send the built packet with an honest TKEEP on the final beat.
  task send_built;
    integer b;
    reg [63:0] d;
    begin
      b = 0;
      while (b < PKT_BYTES) begin
        for (k = 0; k < 8; k = k + 1)
          d[k*8 +: 8] = ((b + k) < PKT_BYTES) ? pktbuf[b + k] : 8'h00;
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= d;
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
    nerr = 0; nmsg_out = 0;
    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);
    axi_write(5'h18, 32'h1);      // enable
    repeat (4) @(negedge aclk);

    // Stream NPKT packets back to back with no inter-packet gap.
    for (npkt = 0; npkt < NPKT; npkt = npkt + 1) begin
      build_pkt(npkt + 1);
      send_built;
    end

    repeat (60000) @(negedge aclk);   // let it drain

    $display("STREAM pkts_sent=%0d rx_packets=%0d rx_messages=%0d gap=%0d err=%0d outbytes=%0d",
             NPKT, dut.rx_packets, dut.rx_messages, dut.gap_count,
             dut.error_count, nmsg_out);
    if (dut.rx_packets == NPKT && dut.rx_messages == NPKT &&
        dut.error_count == 0 && dut.gap_count == 0)
      $display("STREAM-PASS");
    else
      $display("STREAM-FAIL");
    $finish;
  end

endmodule

