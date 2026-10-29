// tb_session_bad2: is the missing byte-0 comparison cold-start only?
//
// Round 122 found that the FIRST packet after enable is accepted regardless of its session,
// because cur_byte is X in ST_SESSION0. This drives TWO packets:
//
//     packet 1   correct session 'NASDAQ01'   - warms the read pipeline
//     packet 2   bad session 'XASDAQ01'       - must be rejected if byte 0 is compared at all
//
// Outcomes:
//     err >= 1  -> the defect is cold-start only; byte 0 is compared once the pipeline is warm
//     err == 0  -> byte 0 is never compared, and the session check is ineffective
`timescale 1ns / 1ps

module tb_session_bad2;

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
  integer   i;
  integer   k;
  integer   nbytes;
  integer   err_before;

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
            1: s_axis_tkeep = 8'h01;
            2: s_axis_tkeep = 8'h03;
            3: s_axis_tkeep = 8'h07;
            4: s_axis_tkeep = 8'h0F;
            5: s_axis_tkeep = 8'h1F;
            6: s_axis_tkeep = 8'h3F;
            7: s_axis_tkeep = 8'h7F;
            default: s_axis_tkeep = 8'hFF;
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
    input [7:0] b0;
    input [7:0] seq_hi;
    input [7:0] seq_lo;
    begin
      pkt[0]=b0;     pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
      pkt[4]=8'h41;  pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
      pkt[8]=seq_hi; pkt[9]=seq_lo;
      pkt[10]=8'h00; pkt[11]=8'h01;
      pkt[12]=8'h00; pkt[13]=8'h04;
      pkt[14]=8'h41; pkt[15]=8'h42; pkt[16]=8'h43; pkt[17]=8'h44;
      nbytes = 18;
    end
  endtask

  // Count each error_count increment and the state that caused it.
  reg [31:0] prev_err = 0;
  always @(posedge aclk) begin
    if (aresetn && dut.error_count != prev_err) begin
      $display("ERRINC t=%0t err=%0d state=%0d rd_ptr=%0d",
               $time, dut.error_count, dut.state, dut.pkt_rd_ptr);
    end
    prev_err <= dut.error_count;
  end

  initial begin
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);

    // Packet 1: CORRECT session, so the read pipeline is warm before the bad one arrives.
    build_packet(8'h4E, 8'h00, 8'h01);
    $display("BAD2-PROBE packet 1 session NASDAQ01 (good)");
    send_packet;
    repeat (300) @(negedge aclk);
    err_before = dut.error_count;
    $display("BAD2-PROBE after packet 1: err=%0d rx_packets=%0d rx_messages=%0d",
             dut.error_count, dut.rx_packets, dut.rx_messages);

    // Packet 2: BAD session byte 0.
    build_packet(8'h58, 8'h00, 8'h02);
    $display("BAD2-PROBE packet 2 session XASDAQ01 (bad)");
    send_packet;
    repeat (400) @(negedge aclk);

    $display("BAD2-PROBE final err=%0d rx_packets=%0d rx_messages=%0d",
             dut.error_count, dut.rx_packets, dut.rx_messages);

    if (dut.error_count > err_before)
      $display("BAD2-PROBE-COLDSTART-ONLY: the second packet's bad session WAS rejected");
    else
      $display("BAD2-PROBE-NEVER-COMPARED: a warmed pipeline still accepted the bad session");

    $finish;
  end

endmodule
