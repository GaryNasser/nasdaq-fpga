// tb_len_vs_gap: does the pause threshold depend on packet length?
//
// Round 128 found the tolerance is 44 cycles for 26-byte packets, 48 breaks it. 48 = 6 words,
// which may or may not be meaningful.
//
// This repeats the gap sweep at two other packet lengths (34 and 50 bytes) and prints the
// threshold for each. If the threshold moves with length, it is an artefact of packet size; if it
// stays at 44-48, it is a pure cycle count.
`timescale 1ns / 1ps

module tb_len_vs_gap;

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
  integer   base;
  integer   b;
  integer   p;
  integer   rem;
  integer   pktlen;
  integer   body;
  integer   firstbad = -1;

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
    input integer len;
    begin
      pktlen = len;
      body   = len - 14;
      for (p = 0; p < NPK; p = p + 1) begin
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
    end
  endtask

  task send_range;
    input integer lo;
    input integer hi;
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

  task probe;
    input integer len;
    input integer gap;
    input integer record;
    begin
      aresetn = 0;
      repeat (6) @(negedge aclk);
      aresetn = 1;
      repeat (4) @(negedge aclk);
      axi_write(5'h18, 32'h1);
      repeat (4) @(negedge aclk);

      for (p = 0; p < NPK; p = p + 1) begin
        send_range(p * len, (p + 1) * len);
        if (gap > 0) repeat (gap) @(negedge aclk);
      end
      repeat (1500) @(negedge aclk);

      if (dut.rx_packets != NPK || dut.error_count != 0) begin
        if (record && firstbad < 0) firstbad = gap;
      end
    end
  endtask

  task sweep_len;
    input integer len;
    begin
      firstbad = -1;
      probe(len, 0,  1);
      probe(len, 16, 1);
      probe(len, 32, 1);
      probe(len, 40, 1);
      probe(len, 44, 1);
      probe(len, 48, 1);
      probe(len, 56, 1);
      probe(len, 64, 1);
      probe(len, 96, 1);
      $display("LVG len=%0d first_bad_gap=%0d", len, firstbad);
    end
  endtask

  initial begin
    build(26);
    sweep_len(26);
    build(34);
    sweep_len(34);
    build(50);
    sweep_len(50);
    $display("LVG-DONE");
    $finish;
  end

endmodule
