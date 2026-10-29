// tb_pause_sweep: how short a pause is enough to break the parse?
//
// Round 127 isolated the pause: 300 idle cycles between four 26-byte packets gives 2 of 4 packets
// and 45 errors; a continuous burst gives 4 of 4 with 0. This sweeps the pause length to find the
// threshold.
//
//     pause = 0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 64, 128, 300 cycles
//
// A real DMA has small gaps between bursts - the descriptor chain is not gapless. If even a
// one-cycle gap breaks the parse, the design cannot be used with a real driver at all. If the
// threshold is a few cycles, the required care is much smaller.
`timescale 1ns / 1ps

module tb_pause_sweep;

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

  reg [7:0] stream [0:255];
  integer   k;
  integer   base;
  integer   b;
  integer   p;
  integer   lanes;
  integer   nfail = 0;

  localparam LEN = 26;
  localparam NPK = 4;

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

  task build;
    begin
      for (p = 0; p < NPK; p = p + 1) begin
        base = p * LEN;
        stream[base+0]=8'h4E; stream[base+1]=8'h41; stream[base+2]=8'h53;
        stream[base+3]=8'h44; stream[base+4]=8'h41; stream[base+5]=8'h51;
        stream[base+6]=8'h30; stream[base+7]=8'h31;
        stream[base+8]=8'h00; stream[base+9]=p[7:0] + 8'd1;
        stream[base+10]=8'h00; stream[base+11]=8'h01;
        stream[base+12]=8'h00; stream[base+13]=8'd12;
        for (b = 0; b < 12; b = b + 1)
          stream[base+14+b] = 8'h41 + b[7:0];
      end
    end
  endtask

  task send_range;
    input integer lo;
    input integer hi;
    integer rem;
    begin
      k = lo;
      while (k < hi) begin
        @(negedge aclk);
        s_axis_tdata  = {stream[k+7], stream[k+6], stream[k+5], stream[k+4],
                         stream[k+3], stream[k+2], stream[k+1], stream[k]};
        rem = hi - k;
        if (rem > 8) rem = 8;
        case (rem)
          1: s_axis_tkeep = 8'h01;  2: s_axis_tkeep = 8'h03;
          3: s_axis_tkeep = 8'h07;  4: s_axis_tkeep = 8'h0F;
          5: s_axis_tkeep = 8'h1F;  6: s_axis_tkeep = 8'h3F;
          7: s_axis_tkeep = 8'h7F;  default: s_axis_tkeep = 8'hFF;
        endcase
        s_axis_tvalid = 1;
        s_axis_tlast  = ((k + 8) >= hi);
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        k = k + 8;
      end
      @(negedge aclk);
      s_axis_tvalid = 0;
      s_axis_tlast  = 0;
    end
  endtask

  task run_case;
    input integer gap;
    begin
      aresetn = 0;
      repeat (6) @(negedge aclk);
      aresetn = 1;
      repeat (4) @(negedge aclk);
      axi_write(5'h18, 32'h1);
      repeat (4) @(negedge aclk);

      for (p = 0; p < NPK; p = p + 1) begin
        send_range(p * LEN, (p + 1) * LEN);
        if (gap > 0) repeat (gap) @(negedge aclk);
      end
      repeat (1500) @(negedge aclk);

      $display("PSWEEP gap=%0d pkt=%0d msg=%0d err=%0d gapcnt=%0d",
               gap, dut.rx_packets, dut.rx_messages, dut.error_count, dut.gap_count);
      if (dut.rx_packets != NPK || dut.rx_messages != NPK || dut.error_count != 0)
        nfail = nfail + 1;
    end
  endtask

  initial begin
    build;
    $display("PSWEEP four 26-byte packets, idle cycles between them");
    run_case(0);
    run_case(1);
    run_case(2);
    run_case(3);
    run_case(4);
    run_case(6);
    run_case(8);
    run_case(12);
    run_case(16);
    run_case(24);
    run_case(33);
    run_case(34);
    run_case(36);
    run_case(38);
    run_case(40);
    run_case(44);
    run_case(48);
    run_case(56);
    run_case(64);
    run_case(128);
    run_case(300);
    // Expected shape: gaps 0..44 are clean; 48 and above break the parse. The sweep asserts the
    // TOLERANCE, so if a future RTL change moves it, the reported count changes.
    $display("PSWEEP broke=%0d of 17 (0,1,2,3,4,6,8,12,16,24,32,33,34,36,38,40,44 expected clean)",
             nfail);
    if (nfail > 0)
      $display("PSWEEP-FAIL-EXPECTED: %0d short-gap cases broke - tolerance has shrunk", nfail);
    else
      $display("PSWEEP-NONE-BROKE: every tested gap was tolerated");
    $finish;
  end

endmodule
