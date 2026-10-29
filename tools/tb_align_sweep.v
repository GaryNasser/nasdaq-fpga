// tb_align_sweep: how much does misalignment cost, and does the packet length matter?
//
// Round 126 established that word-aligned concatenated packets parse cleanly and unaligned ones
// rescan. This sweeps the packet length so the boundary lands in every lane of a word:
//
//     length   boundary offset   lane of the next packet's start
//     24       0                 lane 0   (aligned, control)
//     25       25 mod 8 = 1      lane 1
//     26                        lane 2
//     27                        lane 3
//     28                        lane 4
//     29                        lane 5
//     30                        lane 6
//     31                        lane 7
//     32       0                 lane 0   (aligned again)
//
// Each case sends FOUR concatenated packets of that length in one burst and reports the counters.
// The message body is padded so that 14 + body == length.
`timescale 1ns / 1ps

module tb_align_sweep;

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

  reg [7:0] stream [0:511];
  integer   k;
  integer   nbytes;
  integer   base;
  integer   j;
  integer   pktlen;
  integer   body;
  integer   nfail = 0;

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
    integer lanes;
    begin
      k = 0;
      while (k < nbytes) begin
        @(negedge aclk);
        s_axis_tdata  = {stream[k+7], stream[k+6], stream[k+5], stream[k+4],
                         stream[k+3], stream[k+2], stream[k+1], stream[k]};
        lanes = nbytes - k;
        if (lanes > 8) lanes = 8;
        case (lanes)
          1: s_axis_tkeep = 8'h01;  2: s_axis_tkeep = 8'h03;
          3: s_axis_tkeep = 8'h07;  4: s_axis_tkeep = 8'h0F;
          5: s_axis_tkeep = 8'h1F;  6: s_axis_tkeep = 8'h3F;
          7: s_axis_tkeep = 8'h7F;  default: s_axis_tkeep = 8'hFF;
        endcase
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

  // Build NPK copies of a `pktlen`-byte packet, concatenated.
  task build_stream;
    input integer len;
    integer p;
    integer b;
    begin
      pktlen = len;
      body   = len - 14;
      for (p = 0; p < 4; p = p + 1) begin
        base = p * len;
        stream[base+0]=8'h4E; stream[base+1]=8'h41; stream[base+2]=8'h53;
        stream[base+3]=8'h44; stream[base+4]=8'h41; stream[base+5]=8'h51;
        stream[base+6]=8'h30; stream[base+7]=8'h31;
        stream[base+8]=8'h00; stream[base+9]=p[7:0] + 8'd1;
        stream[base+10]=8'h00; stream[base+11]=8'h01;
        stream[base+12]=8'h00; stream[base+13]=body[7:0];
        for (b = 0; b < body; b = b + 1)
          stream[base+14+b] = 8'h41 + (b % 20);
      end
      nbytes = 4 * len;
    end
  endtask

  task run_case;
    input integer len;
    begin
      // full reset between cases
      aresetn = 0;
      repeat (6) @(negedge aclk);
      aresetn = 1;
      repeat (4) @(negedge aclk);
      axi_write(5'h18, 32'h1);
      repeat (4) @(negedge aclk);

      build_stream(len);
      send_all;
      repeat (2000) @(negedge aclk);

      $display("SWEEP len=%0d lane=%0d pkt=%0d msg=%0d err=%0d gap=%0d",
               len, len % 8, dut.rx_packets, dut.rx_messages, dut.error_count,
               dut.gap_count);
      if (dut.rx_packets != 4 || dut.rx_messages != 4 || dut.error_count != 0)
        nfail = nfail + 1;
    end
  endtask

  initial begin
    $display("SWEEP four concatenated packets per case");
    run_case(24);
    run_case(25);
    run_case(26);
    run_case(27);
    run_case(28);
    run_case(29);
    run_case(30);
    run_case(31);
    run_case(32);
    if (nfail == 0)
      $display("SWEEP-PASS: every length and alignment parsed cleanly");
    else
      $display("SWEEP-FAIL: %0d of 9 cases did not parse cleanly", nfail);
    $display("SWEEP-DONE");
    $finish;
  end

endmodule
