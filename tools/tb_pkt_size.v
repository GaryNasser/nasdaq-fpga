// tb_pkt_size: does a packet the size of the real capture's (1456 bytes) behave differently?
//
// Two refuted mechanisms later, the remaining discriminator is packet SIZE:
//
//     synthetic cases   18 and 32 bytes   -> errors
//     real capture      1456 bytes        -> 850/850 clean
//
// This drives two 1456-byte packets with correct sessions and counts the errors.
//
//     err == 0   size is the discriminator; the synthetic cases simply starve the buffer
//     err  > 0   size is not it either, and the real capture's cleanliness has another cause
`timescale 1ns / 1ps

module tb_pkt_size;

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

  // 1456 bytes per packet = 182 words.
  reg [7:0] pkt [0:1471];
  integer   k;
  integer   nbytes;
  integer   j;

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
        s_axis_tkeep  = 8'hFF;          // every packet here is a multiple of 8
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

  // body length such that 14 + body = 1456
  task build_packet;
    input [7:0] seq_lo;
    integer b;
    begin
      pkt[0]=8'h4E; pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
      pkt[4]=8'h41; pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
      pkt[8]=8'h00; pkt[9]=seq_lo;
      pkt[10]=8'h00; pkt[11]=8'h01;   // one message
      pkt[12]=8'h05; pkt[13]=8'hAE;   // 1454 = 0x05AE
      for (b = 0; b < 1454; b = b + 1)
        pkt[14+b] = 8'h41 + (b % 20);
      nbytes = 1468;
    end
  endtask

  initial begin
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);

    build_packet(8'h01);
    $display("SIZE packet 1: 1468 bytes (183 words)");
    send_packet;
    repeat (2500) @(negedge aclk);
    $display("SIZE after packet 1: rx_packets=%0d err=%0d", dut.rx_packets,
             dut.error_count);

    build_packet(8'h02);
    $display("SIZE packet 2: 1468 bytes");
    send_packet;
    repeat (2500) @(negedge aclk);
    $display("SIZE after packet 2: rx_packets=%0d err=%0d gap=%0d", dut.rx_packets,
             dut.error_count, dut.gap_count);

    if (dut.error_count == 0)
      $display("SIZE-PASS: large packets need no rescan");
    else
      $display("SIZE-FAIL-ERR-%0d: large packets still rescan", dut.error_count);

    $finish;
  end

endmodule
