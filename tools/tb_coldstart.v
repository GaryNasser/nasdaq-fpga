// tb_coldstart: watch rd_valid_d, rd_word_seen and byte_valid_r from reset to the first byte.
//
// The RTL comment says the pipeline needs 3 cycles for pkt_ram_rdata_r to hold real data, and that
// only the FIRST packet of a stream survives - every later packet crosses a word boundary. Our
// measurements say the opposite end is damaged: the first packet's leading Adds are lost.
//
// This drives one packet and prints, every cycle from reset to the first byte consumed, the state
// that decides whether a byte is valid.
`timescale 1ns / 1ps

module tb_coldstart;

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

  reg [7:0] stream [0:63];
  integer   i;
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

  // Print the deciding state every cycle while the FSM is below ST_SEQ_HI (i.e. still in session).
  always @(posedge aclk) begin
    if (aresetn && dut.enable && dut.state <= 18) begin
      $display("COLD t=%0t st=%0d rd_ptr=%0d seen=%0d changed=%b vd=%0d bvr=%b cur=%02x rdata=%016x committed=%0d avail=%0d",
               $time, dut.state, dut.pkt_rd_ptr, dut.rd_word_seen[11:3],
               dut.rd_word_changed, dut.rd_valid_d, dut.byte_valid_r,
               dut.cur_byte, dut.pkt_ram_rdata_r, dut.bytes_committed,
               dut.fifo_available);
    end
  end

  task send_packet;
    begin
      k = 0;
      while (k < nbytes) begin
        @(negedge aclk);
        s_axis_tdata  = {stream[k+7], stream[k+6], stream[k+5], stream[k+4],
                         stream[k+3], stream[k+2], stream[k+1], stream[k]};
        s_axis_tkeep  = 8'hFF;
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
    // One packet: session NASDAQ01, seq 1, one 16-byte message -> 30 bytes
    stream[0]=8'h4E; stream[1]=8'h41; stream[2]=8'h53; stream[3]=8'h44;
    stream[4]=8'h41; stream[5]=8'h51; stream[6]=8'h30; stream[7]=8'h31;
    stream[8]=8'h00; stream[9]=8'h01;
    stream[10]=8'h00; stream[11]=8'h01;
    stream[12]=8'h00; stream[13]=8'h10;
    for (i = 0; i < 16; i = i + 1) stream[14+i] = 8'h41 + i[7:0];
    nbytes = 30;

    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    $display("COLD --- before enable ---");
    axi_write(5'h18, 32'h1);
    // The board's DMA starts long after the driver enables the core: the register writes and the
    // transfer setup take microseconds. Round 128 measured the tolerance at ~44 idle cycles, so a
    // bench that sends immediately never sees the failure.
    repeat (200) @(negedge aclk);
    $display("COLD --- sending after a 200-cycle idle ---");
    send_packet;
    // 200, not 60: the packet's message has to clear the output stage downstream of the reassembler,
    // and the two-cycle entry arm added in round 161 pushed completion two cycles later. 60 cycles
    // after the last byte left the transfer still in flight, reported as pkts=0 err=0.
    repeat (200) @(negedge aclk);
    $display("COLD final st=%0d pkts=%0d msgs=%0d err=%0d", dut.state, dut.rx_packets,
             dut.rx_messages, dut.error_count);
    // The defect: the FSM enters ST_SESSION0 while pkt_ram_rdata_r is still X, so the first
    // session byte is consumed as X. A fix flips this marker instead of passing silently.
    if (dut.rx_messages == 1 && dut.error_count == 0)
      $display("COLD-DIAG-FAIL-XWINDOW: the packet parsed with the X window present");
    else
      $display("COLD-DIAG-OTHER pkts=%0d msgs=%0d err=%0d", dut.rx_packets,
               dut.rx_messages, dut.error_count);
    $finish;
  end

endmodule
