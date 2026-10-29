// tb_parity2: compare every byte the parser consumes against the sent stream.
//
// The previous attempt was off by one: it registered the byte on one edge and
// the pointer on another, so it compared a byte against the wrong position and
// even reported "got=41 want=41" as a mismatch. This version samples the byte
// and the pointer on the SAME edge and only compares a pair once both are
// latched together, and it self-checks that the instrument agrees with reality
// on data whose answer is already known.
`timescale 1ns / 1ps

module tb_parity2;

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

  wire [7:0]  m_axis_tdata;
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

  integer i, k, npkt, ef, b;
  parameter NPKT      = 89;
  parameter MSG_LEN   = 36;
  parameter PKT_BYTES = 50;
  parameter MAXB      = 8192;

  reg [7:0] exp_stream [0:MAXB-1];   // absolute byte offsets
  reg [7:0] pktbuf     [0:PKT_BYTES-1];

  // ---------------------------------------------------------------- monitor
  // Sample the byte and the pointer together, then compare that pair on the
  // NEXT edge when the pointer is seen to have moved. Both halves of the pair
  // come from the same cycle, so there is no skew.
  integer parity_errs;
  integer first_bad;
  integer checked;
  reg [11:0]  p_cur, p_prev;
  reg [7:0]   b_cur, b_prev;
  reg         mon_on;
  integer     wrap_base;

  initial begin
    parity_errs = 0; first_bad = -1; checked = 0;
    mon_on = 0; wrap_base = 0; p_prev = 12'd0; b_prev = 8'd0;
  end

  always @(posedge aclk) begin
    if (aresetn) begin
      // Latch this cycle's (pointer, byte) pair.
      p_cur <= dut.pkt_rd_ptr;
      b_cur <= dut.cur_byte;

      if (mon_on && (p_prev != p_cur)) begin
        // The pointer moved out of p_prev, so b_prev was the byte the parser
        // consumed at position p_prev. Compare it to the stream there.
        checked = checked + 1;
        if (checked > 1 && (b_prev !== exp_stream[p_prev + wrap_base])) begin
          parity_errs = parity_errs + 1;
          if (first_bad < 0) begin
            first_bad = p_prev + wrap_base;
            $display("PARITY-FIRST idx=%0d got=%h want=%h rd=%0d",
                     p_prev + wrap_base, b_prev,
                     exp_stream[p_prev + wrap_base], p_prev);
          end
        end
        if (p_cur == 12'd0 && p_prev != 12'd0) wrap_base = wrap_base + 4096;
      end
      p_prev <= p_cur;
      b_prev <= b_cur;
    end
  end

  // ------------------------------------------------------------- AXI helpers
  task axi_write(input [4:0] a, input [31:0] v);
    begin
      @(negedge aclk);
      s_axi_awaddr <= a; s_axi_awvalid <= 1;
      s_axi_wdata  <= v; s_axi_wvalid  <= 1;
      while (!(s_axi_awready && s_axi_wready)) @(negedge aclk);
      @(negedge aclk);
      s_axi_awvalid <= 0; s_axi_wvalid <= 0;
      while (!s_axi_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  task build_pkt(input [15:0] sq);
    begin
      pktbuf[0]=8'h4E; pktbuf[1]=8'h41; pktbuf[2]=8'h53; pktbuf[3]=8'h44;
      pktbuf[4]=8'h41; pktbuf[5]=8'h51; pktbuf[6]=8'h30; pktbuf[7]=8'h31;
      pktbuf[8]=sq[15:8]; pktbuf[9]=sq[7:0];
      pktbuf[10]=8'h00; pktbuf[11]=8'h01;
      pktbuf[12]=8'h00; pktbuf[13]=MSG_LEN[7:0];
      for (k = 0; k < MSG_LEN; k = k + 1)
        pktbuf[14+k] = (k == 0) ? 8'h41 : (8'h00 | k[7:0]);
    end
  endtask

  task send_built;
    reg [63:0] w;
    begin
      b = 0;
      while (b < PKT_BYTES) begin
        for (k = 0; k < 8; k = k + 1)
          w[k*8 +: 8] = ((b + k) < PKT_BYTES) ? pktbuf[b + k] : 8'h00;
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= w;
        if ((b + 8) > PKT_BYTES) begin
          s_axis_tkeep <= (8'hFF >> (8 - (PKT_BYTES - b)));
          s_axis_tlast <= 1'b1;
        end else begin
          s_axis_tkeep <= 8'hFF;
          s_axis_tlast <= ((b + 8) == PKT_BYTES);
        end
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        b = b + ((b + 8 > PKT_BYTES) ? (PKT_BYTES - b) : 8);
      end
      @(negedge aclk);
      s_axis_tvalid <= 0;
      s_axis_tlast  <= 0;
    end
  endtask

  // ---------------------------------------------------------------- stimulus
  initial begin
    for (npkt = 0; npkt < NPKT; npkt = npkt + 1) begin
      build_pkt(npkt + 1);
      for (ef = 0; ef < PKT_BYTES; ef = ef + 1)
        exp_stream[npkt*PKT_BYTES + ef] = pktbuf[ef];
    end

    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);
    axi_write(5'h18, 32'h1);
    repeat (4) @(negedge aclk);
    mon_on = 1;

    for (npkt = 0; npkt < NPKT; npkt = npkt + 1) begin
      build_pkt(npkt + 1);
      send_built;
    end
    repeat (400000) @(negedge aclk);

    $display("PARITY-TOTAL checked=%0d errs=%0d first_bad=%0d rx_packets=%0d rx_msg=%0d errc=%0d",
             checked, parity_errs, first_bad, dut.rx_packets,
             dut.rx_messages, dut.error_count);

    // The verdict belongs HERE, not in the runner's string match.
    //
    // Until now this testbench printed PARITY-TOTAL unconditionally
    // and then $finish, so the simulation itself could never fail -
    // run_sims.py matched "errs=0 first_bad=-1" in the text, which
    // works but puts the pass condition in the runner. That is the same
    // shape as the original PARITY-TOTAL defect (a token printed on both
    // outcomes): change the display format and the suite silently stops
    // asserting anything.
    //
    // Found by tools/check_suite_asserts.py, which reports any suite
    // whose pass token is not guarded by a condition.
    if (parity_errs == 0 && first_bad < 0
        && dut.rx_packets == NPKT && dut.error_count == 0)
      $display("PARITY-PASS");
    else
      $display("PARITY-FAIL");
    $finish;
  end

endmodule
