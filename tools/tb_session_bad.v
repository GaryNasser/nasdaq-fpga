// tb_session_bad: drive ONE packet with a wrong session and watch the error counter.
//
// Round 120 drove a capture whose first session byte was corrupted ('XASDAQ01') through
// tb_realfile and got rx_packets=850, err=0. The RTL's mismatch branch increments error_count,
// so either the branch never ran or the error was cleared.
//
// This drives a single packet by hand, waits, then reads the counters - no capture, no image, no
// intervening logic. If err stays 0 here, the mismatch path genuinely does not fire for a packet
// whose first byte is wrong.
//
// Unlike tb_session_probe (which tests a CORRECT session), this one is only about rejection.
`timescale 1ns / 1ps

module tb_session_bad;

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

  // bytes[0] is the first byte on the wire; it sits in tdata[7:0].
  reg [7:0] pkt [0:63];
  integer   i;
  integer   nbytes;
  integer   err_seen;

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
    integer k;
    begin
      k = 0;
      while (k < nbytes) begin
        @(negedge aclk);
        s_axis_tdata  = {pkt[k+7], pkt[k+6], pkt[k+5], pkt[k+4],
                         pkt[k+3], pkt[k+2], pkt[k+1], pkt[k]};
        // TKEEP must reflect the bytes actually present on this beat. A packet is not a
        // multiple of 8 bytes, so the last beat carries fewer; marking all eight valid fed the
        // reassembler six phantom bytes and stalled it in ST_SESSION6 waiting for data.
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

  // Record every state change at posedge, where state is valid.
  reg [4:0] prev_state = 5'd0;
  always @(posedge aclk) begin
    if (aresetn && dut.enable && dut.state != prev_state) begin
      $display("STCHG t=%0t from=%0d to=%0d cur=%02x mis_next=%b",
               $time, prev_state, dut.state, dut.cur_byte, dut.session_mis_next);
    end
    prev_state <= dut.state;
  end

  initial begin
    // One packet, session 'XASDAQ01' - the first byte deliberately wrong.
    pkt[0]=8'h58; pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
    pkt[4]=8'h41; pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
    pkt[8]=8'h00; pkt[9]=8'h01;       // seq = 1
    pkt[10]=8'h00; pkt[11]=8'h01;     // count = 1 message
    pkt[12]=8'h00; pkt[13]=8'h04;     // message length 4
    pkt[14]=8'h41; pkt[15]=8'h42; pkt[16]=8'h43; pkt[17]=8'h44;
    nbytes = 18;

    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);

    axi_write(5'h18, 32'h1);          // enable
    repeat (4) @(negedge aclk);

    $display("BAD-PROBE sending a packet with session XASDAQ01");
    send_packet;

    // Trace every cycle the FSM spends in a session state. This shows what it compares.
    for (i = 0; i < 400; i = i + 1) begin
      @(negedge aclk);
      // Every cycle in ST_SESSION0, with the signals that gate it.
      if (dut.state == 1) begin
        $display("S0 cyc=%0d cur=%02x bvr=%b fnel=%b rd_valid_d=%0d word_changed=%b",
                 i, dut.cur_byte, dut.byte_valid_r, dut.fifo_not_empty_live,
                 dut.rd_valid_d, dut.rd_word_changed);
      end
      if ((dut.state >= 1 && dut.state <= 8) || dut.state == 18) begin
        $display("TRACE cyc=%0d st=%0d cur=%02x mis_next=%b mis=%b mm=%b err=%0d",
                 i, dut.state, dut.cur_byte, dut.session_mis_next,
                 dut.session_mis, dut.session_mismatch, dut.error_count);
      end
      if (dut.error_count != 0 && err_seen == 0) begin
        err_seen = 1;
        $display("BAD-PROBE first error at cycle %0d, state=%0d mis=%b",
                 i, dut.state, dut.session_mis);
      end
    end

    // Read the settle value with no traffic: every session state has completed by now.
    $display("BAD-PROBE settled state=%0d mis=%b mm=%b sr0=%02x sr1=%02x sr7=%02x",
             dut.state, dut.session_mis, dut.session_mismatch,
             dut.session_sr[0], dut.session_sr[1], dut.session_sr[7]);
    $display("BAD-PROBE final err=%0d rx_packets=%0d rx_messages=%0d",
             dut.error_count, dut.rx_packets, dut.rx_messages);

    if (dut.error_count == 0 && dut.rx_messages == 0)
      $display("BAD-PROBE-REJECTED-SILENTLY: the packet was dropped but no error was counted");
    else if (dut.error_count > 0)
      $display("BAD-PROBE-ERROR-COUNTED: err=%0d messages=%0d",
               dut.error_count, dut.rx_messages);
    else
      $display("BAD-PROBE-FAIL-ACCEPTED: a bad session was accepted, err=0 messages=%0d",
               dut.rx_messages);

    $finish;
  end

  initial begin
    err_seen = 0;
  end

endmodule
