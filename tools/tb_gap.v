// tb_gap: how much source stalling does it take to break the reassembler?
//
// The previous round found that a source inserting up to 7 idle cycles before
// beats collapses the design (0 of 2 packets). Before treating that as a
// design defect the stimulus has to be calibrated: a real DMA pauses between
// beats for a few cycles constantly, so even ONE idle cycle between packets
// must be survivable.
//
// This sweeps the gap: 0 (continuous), 1 cycle between packets, and 1 cycle
// between every beat. A design that needs a continuously-driven source is not
// usable on hardware.
`timescale 1ns / 1ps

module tb_gap;

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

  parameter NPKT      = 20;
  parameter MSG_LEN   = 36;      // 1 message per packet
  parameter PKT_BYTES = 50;
  parameter GAP_BEAT  = 0;       // idle cycles inserted before every beat

  reg [7:0] pktbuf [0:PKT_BYTES-1];
  integer k, b, npkt;

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
    integer done;
    begin
      b = 0;
      while (b < PKT_BYTES) begin
        done = (PKT_BYTES - b) < 8 ? (PKT_BYTES - b) : 8;
        for (k = 0; k < 8; k = k + 1)
          w[k*8 +: 8] = (k < done) ? pktbuf[b + k] : 8'h00;
        // A stalled source must hold TVALID LOW, not merely pause between
        // updates: with TVALID still high the receiver would legitimately
        // accept the same beat again and the "gap" would inject duplicates.
        // (An earlier version of this generator did exactly that and made the
        // DUT look broken under a stimulus that was itself invalid.)
        if (GAP_BEAT > 0) begin
          s_axis_tvalid <= 0;
          repeat (GAP_BEAT) @(negedge aclk);
        end
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= w;
        s_axis_tkeep  <= (done == 8) ? 8'hFF : ((8'hFF >> (8 - done)));
        s_axis_tlast  <= ((b + done) == PKT_BYTES);
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        b = b + done;
      end
      @(negedge aclk);
      s_axis_tvalid <= 0;
      s_axis_tlast  <= 0;
    end
  endtask

  initial begin
    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);

    for (npkt = 0; npkt < NPKT; npkt = npkt + 1) begin
      build_pkt(npkt + 1);
      send_built;
      // One idle cycle between packets: the minimum realistic DMA behaviour.
      @(negedge aclk);
    end

    repeat (200000) @(negedge aclk);

    $display("GAP pkts=%0d rx_packets=%0d rx_messages=%0d gap=%0d err=%0d",
             NPKT, dut.rx_packets, dut.rx_messages, dut.gap_count,
             dut.error_count);
    if (dut.rx_packets == NPKT && dut.rx_messages == NPKT &&
        dut.gap_count == 0 && dut.error_count == 0)
      $display("GAP-PASS");
    else
      $display("GAP-FAIL");
    $finish;
  end

endmodule
