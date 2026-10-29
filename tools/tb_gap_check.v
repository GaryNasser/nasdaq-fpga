// tb_gap_check: does the sequence-gap detector actually detect a gap?
//
// Rounds 122-123 found the session check had holes. The same question applies to the sequence
// number: the design tracks expect_seq and increments gap_count when rx_seq > expect_seq.
//
// Three packets, all with a GOOD session:
//     packet 1  seq=1   expected, no gap
//     packet 2  seq=2   expected, no gap
//     packet 3  seq=9   a gap of 6
//
// Expected: gap_count == 1 after packet 3 (one detected gap, not six). If it stays 0, gap
// detection does not work; if it is 6, the counter counts missing packets rather than gaps -
// either is finer-grained information than the existing tb_gap.v gives, which sweeps stalls
// rather than sequence numbers.
`timescale 1ns / 1ps

module tb_gap_check;

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

  reg [7:0] pkt [0:63];
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

  task build_packet;
    input [7:0] seq_hi;
    input [7:0] seq_lo;
    begin
      pkt[0]=8'h4E; pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
      pkt[4]=8'h41; pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
      pkt[8]=seq_hi; pkt[9]=seq_lo;
      pkt[10]=8'h00; pkt[11]=8'h01;    // count 1
      pkt[12]=8'h00; pkt[13]=8'h04;    // msg len 4
      pkt[14]=8'h41; pkt[15]=8'h42; pkt[16]=8'h43; pkt[17]=8'h44;
      nbytes = 18;
    end
  endtask

  // Trace every error increment with the state and read pointer.
  reg [31:0] prev_err = 0;
  always @(posedge aclk) begin
    if (aresetn && dut.error_count != prev_err) begin
      $display("GAPERR t=%0t err=%0d state=%0d rd_ptr=%0d seq=%0d",
               $time, dut.error_count, dut.state, dut.pkt_rd_ptr, dut.rx_seq);
    end
    prev_err <= dut.error_count;
  end

  initial begin
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);

    build_packet(8'h00, 8'h01);
    $display("GAP-CHK seq=1");
    send_packet;
    repeat (250) @(negedge aclk);
    $display("GAP-CHK after seq=1: gap=%0d rx_packets=%0d", dut.gap_count,
             dut.rx_packets);

    build_packet(8'h00, 8'h02);
    $display("GAP-CHK seq=2");
    send_packet;
    repeat (250) @(negedge aclk);
    $display("GAP-CHK after seq=2: gap=%0d rx_packets=%0d", dut.gap_count,
             dut.rx_packets);

    build_packet(8'h00, 8'h09);
    $display("GAP-CHK seq=9 (a gap of 6)");
    send_packet;
    repeat (300) @(negedge aclk);
    $display("GAP-CHK after seq=9: gap=%0d rx_packets=%0d err=%0d", dut.gap_count,
             dut.rx_packets, dut.error_count);

    if (dut.gap_count == 1)
      $display("GAP-CHK-PASS: one gap detected");
    else
      $display("GAP-CHK-GAP-COUNT-IS-%0d: expected 1", dut.gap_count);

    $finish;
  end

endmodule
