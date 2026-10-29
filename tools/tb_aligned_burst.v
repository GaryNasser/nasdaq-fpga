// tb_aligned_burst: concatenated packets whose length is a multiple of 8, correct TKEEP.
//
// Round 125 concluded alignment was irrelevant because aligned 32-byte packets gave MORE errors
// than unaligned 18-byte ones. But that bench sent each packet separately with its own tkeep
// masking, and this round found that a missing tkeep mask can feed phantom bytes.
//
// This is the clean version: ONE buffer holding concatenated 24-byte packets (14-byte header +
// 10-byte message body), sent as a single continuous burst with correct tkeep on the final beat.
//
//   24 bytes = 3 words exactly, so every packet boundary is word aligned.
//
//     err=0 rx_packets=3   -> alignment is what makes the real capture clean
//     err>0                -> alignment is irrelevant
`timescale 1ns / 1ps

module tb_aligned_burst;

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

  // Three concatenated 24-byte packets = 72 bytes = 9 words exactly.
  reg [7:0] stream [0:71];
  integer   k;
  integer   nbytes;
  integer   base;
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

  task send_all;
    begin
      k = 0;
      while (k < nbytes) begin
        @(negedge aclk);
        s_axis_tdata  = {stream[k+7], stream[k+6], stream[k+5], stream[k+4],
                         stream[k+3], stream[k+2], stream[k+1], stream[k]};
        s_axis_tkeep  = 8'hFF;               // always a whole word here
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

  // One 24-byte packet at offset `base`: header 14, message body 10.
  task put_packet;
    input integer base;
    input [7:0]   seq_lo;
    begin
      stream[base+0]=8'h4E; stream[base+1]=8'h41; stream[base+2]=8'h53;
      stream[base+3]=8'h44; stream[base+4]=8'h41; stream[base+5]=8'h51;
      stream[base+6]=8'h30; stream[base+7]=8'h31;
      stream[base+8]=8'h00; stream[base+9]=seq_lo;
      stream[base+10]=8'h00; stream[base+11]=8'h01;   // one message
      stream[base+12]=8'h00; stream[base+13]=8'h0A;   // 10-byte message
      for (j = 0; j < 10; j = j + 1)
        stream[base+14+j] = 8'h41 + j[7:0];
    end
  endtask

  initial begin
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);

    put_packet(0,  8'h01);
    put_packet(24, 8'h02);
    put_packet(48, 8'h03);
    nbytes = 72;

    $display("ALIGNED three 24-byte packets, one burst, 72 bytes = 9 words");
    send_all;
    repeat (1500) @(negedge aclk);

    $display("ALIGNED-BURST rx_packets=%0d rx_messages=%0d err=%0d gap=%0d",
             dut.rx_packets, dut.rx_messages, dut.error_count, dut.gap_count);

    if (dut.rx_packets == 3 && dut.rx_messages == 3 && dut.error_count == 0)
      $display("ALIGNED-PASS: aligned concatenated packets parse with no rescan");
    else
      $display("ALIGNED-FAIL: expected 3 packets, 3 messages, 0 errors");

    $finish;
  end

endmodule
