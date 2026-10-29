// tb_word_align: does a word-aligned packet length avoid the rescan entirely?
//
// Round 125's mechanism predicts: with an 18-byte packet every boundary lands mid-word and the
// next packet's session compares against stale lanes -> rescan + errors. With a 16-byte message
// body (24-byte packet, a multiple of 8) every boundary is word-aligned and there should be no
// rescan and no errors.
//
// Same code path, same session, only the length differs. If errors vanish at 32 bytes, the
// mechanism is confirmed from the other direction.
`timescale 1ns / 1ps

module tb_word_align;

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
  integer   body;

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

  // body = message length; packet length becomes 14 + body.
  task build_packet;
    input [7:0] seq_lo;
    input integer blen;
    integer j;
    begin
      pkt[0]=8'h4E; pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
      pkt[4]=8'h41; pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
      pkt[8]=8'h00; pkt[9]=seq_lo;
      pkt[10]=8'h00; pkt[11]=8'h01;
      pkt[12]=8'h00; pkt[13]=blen[7:0];
      for (j = 0; j < blen; j = j + 1)
        pkt[14+j] = 8'h41 + j[7:0];
      nbytes = 14 + blen;
    end
  endtask

  initial begin
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);

    // ---- 18-byte packets: boundary NOT word aligned ----
    build_packet(8'h01, 4);
    $display("ALIGN case A: 18-byte packets (not word aligned)");
    send_packet;
    repeat (300) @(negedge aclk);
    build_packet(8'h02, 4);
    send_packet;
    repeat (600) @(negedge aclk);
    $display("ALIGN A: rx_packets=%0d err=%0d gap=%0d", dut.rx_packets,
             dut.error_count, dut.gap_count);

    // ---- reset, then 32-byte packets: boundary word aligned ----
    axi_write(5'h14, 32'h1);   // soft reset
    repeat (10) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (10) @(negedge aclk);

    build_packet(8'h01, 18);   // 14 + 18 = 32 bytes
    $display("ALIGN case B: 32-byte packets (word aligned)");
    send_packet;
    repeat (300) @(negedge aclk);
    build_packet(8'h02, 18);
    send_packet;
    repeat (600) @(negedge aclk);
    $display("ALIGN B: rx_packets=%0d err=%0d gap=%0d", dut.rx_packets,
             dut.error_count, dut.gap_count);

    if (dut.error_count == 0)
      $display("ALIGN-PASS: word-aligned packets need no rescan (mechanism confirmed)");
    else
      $display("ALIGN-ERRORS-REMAIN: %0d", dut.error_count);

    $finish;
  end

endmodule
