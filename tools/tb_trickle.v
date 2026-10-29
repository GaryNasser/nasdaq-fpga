// tb_trickle: deliver the session bytes a few at a time, with the FSM enabled from the start.
//
// The board reports rx_packets=0, rx_messages=0, err=1456 on a 1463-byte single packet - the
// session search fails at every offset. The full 1.2 MB capture works.
//
// The difference is SIZE, and the mechanism this points at is: `fifo_not_empty_live` is true from
// the first committed byte, the FSM enters ST_SESSION0 and tries to read 8 session bytes, and if
// fewer are buffered the comparison fails. The rescan then needs 8 bytes again at every retry.
//
// No existing bench does this: they present a whole beat (8 bytes) before enabling, so the session
// is always fully buffered.
//
// This drives the packet 2 bytes per beat with the FSM enabled first, so the buffer lags. If it
// reports rx_packets=0 and err large, the defect reproduces in simulation and can be fixed there.
`timescale 1ns / 1ps

module tb_trickle;

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
    .m_axis_tdata(m_tdata), .m_axis_tkeep(m_tkeep),
    .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready)
  );

  reg [7:0] pkt [0:63];
  integer   i;
  integer   nbytes;

  task axi_write;
    input [4:0]  addr;
    input [31:0] data;
    begin
      @(negedge aclk);
      awaddr = addr; wdata = data; awvalid = 1; wvalid = 1;
      @(posedge aclk);
      for (i = 0; i < 50 && !(awready && wready); i = i + 1) @(posedge aclk);
      @(negedge aclk);
      awvalid = 0; wvalid = 0;
    end
  endtask

  // Send ONE byte per beat, tkeep = 8'h01, so the FIFO gains a byte at a time.
  task send_trickle;
    integer k;
    begin
      k = 0;
      while (k < nbytes) begin
        @(negedge aclk);
        s_tdata  = {56'd0, pkt[k]};
        s_tkeep  = 8'h01;
        s_tvalid = 1;
        s_tlast  = ((k + 1) >= nbytes);
        @(posedge aclk);
        i = 0;
        while (!s_tready && i < 4000) begin
          @(posedge aclk);
          i = i + 1;
        end
        if (!s_tready)
          $display("TRICKLE-STALL at byte %0d state=%0d", k, dut.state);
        k = k + 1;
      end
      @(negedge aclk);
      s_tvalid = 0;
      s_tlast  = 0;
    end
  endtask

  initial begin
    // Session NASDAQ01, seq 1, one 36-byte message -> 50 bytes
    pkt[0]=8'h4E; pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
    pkt[4]=8'h41; pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
    pkt[8]=8'h00; pkt[9]=8'h01;
    pkt[10]=8'h00; pkt[11]=8'h01;
    pkt[12]=8'h00; pkt[13]=8'h24;
    for (i = 0; i < 36; i = i + 1) pkt[14+i] = (i == 0) ? 8'h41 : (8'h10 + i[7:0]);
    nbytes = 50;

    aresetn = 0;
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);

    // Enable FIRST, so the FSM is armed before any byte exists.
    axi_write(5'h18, 32'h1);   // 0x18 = CTRL, awaddr[4:2] == 6
    repeat (3) @(negedge aclk);

    send_trickle;
    repeat (400) @(negedge aclk);

    $display("TRICKLE rx_packets=%0d rx_messages=%0d err=%0d gap=%0d",
             dut.rx_packets, dut.rx_messages, dut.error_count, dut.gap_count);

    if (dut.rx_packets == 1 && dut.error_count == 0)
      $display("TRICKLE-CLEAN: a trickled session parses");
    else
      $display("TRICKLE-FAIL-REPRODUCED: pkts=%0d err=%0d", dut.rx_packets,
               dut.error_count);

    $finish;
  end

endmodule
