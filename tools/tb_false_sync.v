// tb_false_sync: can a payload containing the session id be mistaken for a packet start?
//
// Round 123 found that on a session mismatch the design slides an 8-byte window through the
// packet rather than dropping it. If the payload contains 'NASDAQ01', the rescan could lock onto
// it and read a bogus header from the following bytes.
//
// Round 122 found that the FIRST packet after enable has its session byte 0 uncompared, so a
// bad-session first packet is accepted regardless of this hazard. To isolate the false-sync
// question the first packet must therefore be a GOOD one, warming both the pipeline and the
// byte-0 comparison.
//
//     packet 1  good session 'NASDAQ01', seq=1, one message   (warms the design)
//     packet 2  bad session 'XASDAQ01', payload contains 'NASDAQ01' + a plausible header
//
// Expected if there is no false sync: after packet 2, rx_packets stays 1 and rx_messages stays 1.
// Expected if the rescan locks on:    rx_packets or rx_messages grows, or a gap is counted.
`timescale 1ns / 1ps

module tb_false_sync;

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

  wire [63:0] m_axis_tdata;
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

  reg [7:0] pkt [0:127];
  integer   k;
  integer   nbytes;

  task axi_write;
    input [4:0]  addr;
    input [31:0] data;
    begin
      @(negedge aclk);
      s_axi_awaddr = addr; s_axi_wdata = data;
      s_axi_awvalid = 1;   s_axi_wvalid = 1;
      @(posedge aclk);
      while (!(s_axi_awready && s_axi_wready)) @(posedge aclk);
      @(negedge aclk);
      s_axi_awvalid = 0; s_axi_wvalid = 0;
    end
  endtask

  task send_packet;
    begin
      k = 0;
      while (k < nbytes) begin
        @(negedge aclk);
        s_axis_tdata  = {pkt[k+7], pkt[k+6], pkt[k+5], pkt[k+4],
                         pkt[k+3], pkt[k+2], pkt[k+1], pkt[k]};
        if ((k + 8) > nbytes) begin
          case (nbytes - k)
            1: s_axis_tkeep = 8'h01;  2: s_axis_tkeep = 8'h03;
            3: s_axis_tkeep = 8'h07;  4: s_axis_tkeep = 8'h0F;
            5: s_axis_tkeep = 8'h1F;  6: s_axis_tkeep = 8'h3F;
            7: s_axis_tkeep = 8'h7F;  default: s_axis_tkeep = 8'hFF;
          endcase
        end else begin
          s_axis_tkeep = 8'hFF;
        end
        s_axis_tvalid = 1;
        s_axis_tlast  = ((k + 8) >= nbytes);
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        k = k + 8;
      end
      @(negedge aclk);
      s_axis_tvalid = 0;
      s_axis_tlast  = 0;
    end
  endtask

  initial begin
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);

    // ---- packet 1: good session, one message ----
    pkt[0]=8'h4E; pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
    pkt[4]=8'h41; pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
    pkt[8]=8'h00; pkt[9]=8'h01;
    pkt[10]=8'h00; pkt[11]=8'h01;
    pkt[12]=8'h00; pkt[13]=8'h04;
    pkt[14]=8'h41; pkt[15]=8'h42; pkt[16]=8'h43; pkt[17]=8'h44;
    nbytes = 18;
    $display("FS-PROBE packet 1: good session (warms the design)");
    send_packet;
    repeat (300) @(negedge aclk);
    $display("FS-PROBE after packet 1: err=%0d rx_packets=%0d rx_messages=%0d",
             dut.error_count, dut.rx_packets, dut.rx_messages);

    // ---- packet 2: bad session, payload carries 'NASDAQ01' and a plausible header ----
    pkt[0]=8'h58;  pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
    pkt[4]=8'h41;  pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
    pkt[8]=8'h00;  pkt[9]=8'h02;
    pkt[10]=8'h00; pkt[11]=8'h02;
    pkt[12]=8'h00; pkt[13]=8'h08;
    pkt[14]=8'h41; pkt[15]=8'h42;
    pkt[16]=8'h4E; pkt[17]=8'h41; pkt[18]=8'h53; pkt[19]=8'h44;
    pkt[20]=8'h41; pkt[21]=8'h51; pkt[22]=8'h30; pkt[23]=8'h31;
    pkt[24]=8'h00; pkt[25]=8'h03;
    pkt[26]=8'h00; pkt[27]=8'h01;
    pkt[28]=8'h00; pkt[29]=8'h04;
    pkt[30]=8'h44; pkt[31]=8'h45; pkt[32]=8'h46; pkt[33]=8'h47;
    nbytes = 34;
    $display("FS-PROBE packet 2: bad session, payload contains NASDAQ01 at offset 16");
    send_packet;
    repeat (900) @(negedge aclk);

    $display("FS-PROBE after packet 2: err=%0d rx_packets=%0d rx_messages=%0d",
             dut.error_count, dut.rx_packets, dut.rx_messages);

    if (dut.rx_messages > 1 || dut.rx_packets > 1)
      $display("FS-PROBE-FAIL-FALSE-SYNC: the rescan locked onto the payload");
    else
      $display("FS-PROBE-NO-SYNC: the bad packet was discarded, payload ignored");

    $finish;
  end

endmodule
