// tb_pause_test: the same packet length with and without a pause. Only one variable changes.
//
// Round 127's sweep showed every length is clean in a continuous burst. Round 126 said unaligned
// packets fail. Those disagree, and the difference must be the pause - but no test has varied the
// pause while holding the length fixed.
//
//    case 1   four 26-byte packets, ONE burst             (continuous)
//    case 2   four 26-byte packets, 300 cycles apart      (paused)
//
// 26 is unaligned (lane 2). If case 1 is clean and case 2 is not, the pause is the cause and the
// length is irrelevant - the cleanest possible statement of the mechanism.
`timescale 1ns / 1ps

module tb_pause_test;

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
  integer   nbytes;
  integer   base;
  integer   b;
  integer   p;
  integer   lanes;
  integer   errC;
  integer   errP;

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
        stream[base+12]=8'h00; stream[base+13]=8'd12;   // 26 - 14
        for (b = 0; b < 12; b = b + 1)
          stream[base+14+b] = 8'h41 + b[7:0];
      end
      nbytes = NPK * LEN;
    end
  endtask

  // Send bytes [lo, hi) as beats, tkeep masking the tail.
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

  task reset_dut;
    begin
      aresetn = 0;
      repeat (6) @(negedge aclk);
      aresetn = 1;
      repeat (4) @(negedge aclk);
      axi_write(5'h18, 32'h1);
      repeat (4) @(negedge aclk);
    end
  endtask

  initial begin
    build;

    // ---- case 1: continuous ----
    reset_dut;
    $display("PAUSE case 1: %0d-byte packets, continuous burst", LEN);
    send_range(0, nbytes);
    repeat (2000) @(negedge aclk);
    errC = dut.error_count;
    $display("PAUSE continuous: pkt=%0d msg=%0d err=%0d gap=%0d", dut.rx_packets,
             dut.rx_messages, errC, dut.gap_count);

    // ---- case 2: paused between packets ----
    reset_dut;
    $display("PAUSE case 2: %0d-byte packets, 300 cycles apart", LEN);
    for (p = 0; p < NPK; p = p + 1) begin
      send_range(p * LEN, (p + 1) * LEN);
      repeat (300) @(negedge aclk);
    end
    repeat (2000) @(negedge aclk);
    errP = dut.error_count;
    $display("PAUSE paused:     pkt=%0d msg=%0d err=%0d gap=%0d", dut.rx_packets,
             dut.rx_messages, errP, dut.gap_count);

    $display("PAUSE-SUMMARY continuous_err=%0d paused_err=%0d", errC, errP);
    if (errC == 0 && errP > 0)
      $display("PAUSE-CONFIRMED: the pause alone causes the rescan");
    else if (errC == 0 && errP == 0)
      $display("PAUSE-NO-EFFECT: both clean at %0d bytes", LEN);
    else
      $display("PAUSE-OTHER: continuous_err=%0d paused_err=%0d", errC, errP);

    $finish;
  end

endmodule
