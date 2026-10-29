// tb_varsize: sustained streaming with REALISTIC and VARIED packet sizes.
//
// Every streaming test so far used a uniform 50-byte packet. Real MoldUDP64
// traffic from the capture is ~1463 bytes per packet, carrying many ITCH
// messages, with sizes varying per packet. This exercises:
//   * multi-message packets (count > 1)
//   * large packets spanning many RAM words
//   * varying sizes, so packet boundaries land on every alignment
`timescale 1ns / 1ps

module tb_varsize;

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

  parameter NPKT     = 40;
  parameter MSG_BYTES = 36;   // ITCH-shaped message body

  // One packet is built at a time; up to 1500 bytes.
  reg [7:0] pb [0:1599];
  integer   nmsg, plen;
  integer   i, k, b, npkt;
  integer   total_msgs;

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

  // Build a packet with `nmsg` messages, giving a realistic size, and a body
  // whose bytes encode (packet index, message index, byte index) so any
  // misplacement is detectable.
  task build_var(input integer idx);
    integer m, q;
    begin
      // Vary message count 1..30 -> packet sizes ~52..1100 bytes, all
      // alignments covered as sizes change by one message each packet.
      nmsg = (idx % 30) + 1;
      q = 0;
      pb[0]=8'h4E; pb[1]=8'h41; pb[2]=8'h53; pb[3]=8'h44;
      pb[4]=8'h41; pb[5]=8'h51; pb[6]=8'h30; pb[7]=8'h31;
      pb[8] = idx[15:8]; pb[9] = idx[7:0];
      pb[10]= nmsg[15:8]; pb[11]= nmsg[7:0];
      q = 12;
      for (m = 0; m < nmsg; m = m + 1) begin
        pb[q] = 8'h00; pb[q+1] = MSG_BYTES[7:0];
        q = q + 2;
        for (k = 0; k < MSG_BYTES; k = k + 1) begin
          pb[q] = 8'h41 ^ idx[7:0] ^ m[7:0] ^ k[7:0];
          q = q + 1;
        end
      end
      plen = q;
    end
  endtask

  task send_var;
    reg [63:0] w;
    begin
      b = 0;
      while (b < plen) begin
        for (k = 0; k < 8; k = k + 1)
          w[k*8 +: 8] = ((b + k) < plen) ? pb[b + k] : 8'h00;
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= w;
        if ((b + 8) > plen) begin
          s_axis_tkeep <= (8'hFF >> (8 - (plen - b)));
          s_axis_tlast <= 1'b1;
        end else begin
          s_axis_tkeep <= 8'hFF;
          s_axis_tlast <= ((b + 8) == plen);
        end
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        b = b + ((b + 8 > plen) ? (plen - b) : 8);
      end
      @(negedge aclk);
      s_axis_tvalid <= 0;
      s_axis_tlast  <= 0;
    end
  endtask

  initial begin
    total_msgs = 0;
    // build_var is called with idx = npkt + 1, so the message count for a
    // packet is ((idx % 30) + 1) with idx starting at 1 - not at 0.
    for (i = 1; i <= NPKT; i = i + 1)
      total_msgs = total_msgs + ((i % 30) + 1);   // i is the 1-based packet index

    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);

    for (npkt = 0; npkt < NPKT; npkt = npkt + 1) begin
      build_var(npkt + 1);
      send_var;
    end
    repeat (4000000) @(negedge aclk);

    $display("VARSIZE pkts=%0d msgs_built=%0d rx_packets=%0d rx_messages=%0d gap=%0d err=%0d",
             NPKT, total_msgs, dut.rx_packets, dut.rx_messages,
             dut.gap_count, dut.error_count);
    if (dut.rx_packets == NPKT && dut.rx_messages == total_msgs &&
        dut.error_count == 0 && dut.gap_count == 0)
      $display("VARSIZE-PASS");
    else
      $display("VARSIZE-FAIL");
    $finish;
  end

endmodule
