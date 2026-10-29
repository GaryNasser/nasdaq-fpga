// tb_enable_race: present data in the SAME cycle the enable write lands.
//
// Round 142 gave the board defect an exact signature: err equals the first packet's byte length,
// because the session comparison never matches while the read pipeline is being primed.
//
// Every existing bench enables the core, waits a few cycles, THEN sends. The board has
// s_axis_tvalid already high when the DMA starts beating - the enable and the first data are
// concurrent.
//
// This drives tvalid high BEFORE the enable write completes, so the first bytes are already in
// flight when the core wakes up.
//
// Expected if it reproduces: rx_packets=0 and err == the packet's byte length.
`timescale 1ns / 1ps

module tb_enable_race;

  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;

  reg  [4:0]  awaddr = 0;
  reg         awvalid = 0;
  wire        awready;
  reg  [31:0] wdata = 0;
  reg         wvalid = 0;
  wire        wready;
  wire [1:0]  bresp;
  wire        bvalid;
  reg         bready = 1;
  reg  [4:0]  araddr = 0;
  reg         arvalid = 0;
  wire        arready;
  wire [31:0] rdata;
  wire [1:0]  rresp;
  wire        rvalid;
  reg         rready = 1;

  reg  [63:0] s_tdata = 0;
  reg  [7:0]  s_tkeep = 8'hFF;
  reg         s_tvalid = 0;
  reg         s_tlast = 0;
  wire        s_tready;

  wire [63:0] m_tdata;
  wire [7:0]  m_tkeep;
  wire        m_tvalid;
  wire        m_tready;

  assign m_tready = 1'b1;

  mold64_reasm #(.SESSION(64'h4E41534441513031)) dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid),
    .s_axi_awready(awready), .s_axi_wdata(wdata), .s_axi_wstrb(5'h1F),
    .s_axi_wvalid(wvalid), .s_axi_wready(wready), .s_axi_bresp(bresp),
    .s_axi_bvalid(bvalid), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid),
    .s_axi_arready(arready), .s_axi_rdata(rdata), .s_axi_rresp(rresp),
    .s_axi_rvalid(rvalid), .s_axi_rready(rready),
    .s_axis_tdata(s_tdata), .s_axis_tkeep(s_tkeep), .s_axis_tvalid(s_tvalid),
    .s_axis_tready(s_tready), .s_axis_tlast(s_tlast),
    .m_axis_tdata(m_tdata), .m_axis_tkeep(m_tkeep), .m_axis_tvalid(m_tvalid),
    .m_axis_tready(m_tready)
  );

  reg [7:0] pkt [0:63];
  integer   i;
  integer   nbytes;
  integer   sent;

  initial begin
    // Session NASDAQ01, seq 1, two 36-byte messages -> 86 bytes
    pkt[0]=8'h4E; pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
    pkt[4]=8'h41; pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
    pkt[8]=8'h00; pkt[9]=8'h01;
    pkt[10]=8'h00; pkt[11]=8'h02;
    pkt[12]=8'h00; pkt[13]=8'h24;
    for (i = 0; i < 36; i = i + 1) pkt[14+i] = (i == 0) ? 8'h41 : (8'h10 + i[7:0]);
    pkt[50]=8'h00; pkt[51]=8'h24;
    for (i = 0; i < 36; i = i + 1) pkt[52+i] = (i == 0) ? 8'h41 : (8'h20 + i[7:0]);
    nbytes = 88;

    aresetn = 0;
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);

    // Present the FIRST BEAT before the enable write, so it is already in flight.
    @(negedge aclk);
    s_tdata  = {pkt[7], pkt[6], pkt[5], pkt[4], pkt[3], pkt[2], pkt[1], pkt[0]};
    s_tkeep  = 8'hFF;
    s_tvalid = 1;
    s_tlast  = 0;

    // Enable one cycle later.
    @(negedge aclk);
    awaddr = 5'h18; wdata = 32'h1; awvalid = 1; wvalid = 1;
    @(posedge aclk);
    for (i = 0; i < 50 && !(awready && wready); i = i + 1) @(posedge aclk);
    @(negedge aclk);
    awvalid = 0; wvalid = 0;

    // Wait for that first beat to be taken, then stream the rest.
    for (i = 0; i < 200 && !s_tready; i = i + 1) @(posedge aclk);
    sent = 8;
    while (sent < nbytes) begin
      @(negedge aclk);
      s_tdata  = {pkt[sent+7], pkt[sent+6], pkt[sent+5], pkt[sent+4],
                  pkt[sent+3], pkt[sent+2], pkt[sent+1], pkt[sent]};
      if ((sent + 8) > nbytes) begin
        case (nbytes - sent)
          1: s_tkeep = 8'h01;  2: s_tkeep = 8'h03;
          3: s_tkeep = 8'h07;  4: s_tkeep = 8'h0F;
          5: s_tkeep = 8'h1F;  6: s_tkeep = 8'h3F;
          7: s_tkeep = 8'h7F;  default: s_tkeep = 8'hFF;
        endcase
      end else begin
        s_tkeep = 8'hFF;
      end
      s_tvalid = 1;
      s_tlast  = ((sent + 8) >= nbytes);
      @(posedge aclk);
      i = 0;
      while (!s_tready && i < 2000) begin
        @(posedge aclk);
        i = i + 1;
      end
      sent = sent + 8;
    end
    @(negedge aclk);
    s_tvalid = 0;
    s_tlast  = 0;

    repeat (600) @(negedge aclk);

    $display("ERACE rx_packets=%0d rx_messages=%0d err=%0d gap=%0d (packet is %0d bytes)",
             dut.rx_packets, dut.rx_messages, dut.error_count, dut.gap_count, nbytes);

    if (dut.rx_packets == 1 && dut.error_count == 0)
      $display("ERACE-CLEAN: the packet parsed");
    else
      $display("ERACE-FAIL-REPRODUCED: pkts=%0d err=%0d", dut.rx_packets,
               dut.error_count);

    $finish;
  end

endmodule
