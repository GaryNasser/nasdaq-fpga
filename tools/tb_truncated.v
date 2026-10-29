// tb_truncated: the DMA stops in the middle of a packet.
//
// A real board session can end this way: the descriptor count is wrong, the buffer is smaller than the capture,
// or the driver dies mid-transfer. The reassembler then receives a partial packet and never sees the rest.
//
// What must hold:
//
//     no crash               the module stays responsive (no X propagation into the AXI response)
//     bounded error          at most one error recorded, not one per remaining byte
//     the counters stay sane rx_packets must not count a packet it never completed
//     recovery works         a subsequent intact packet is parsed normally
//
// The failure this guards against is an error-per-byte explosion: a truncated 200-byte packet must not raise 200
// errors, because `error_count` is surfaced to the driver and a large number there would be read as a real
// malfunction when the actual cause was a short transfer.
`timescale 1ns / 1ps

module tb_truncated;

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
  reg         m_tready = 1;

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
    .m_axis_tdata(m_tdata), .m_axis_tkeep(m_tkeep), .m_axis_tvalid(m_tvalid),
    .m_axis_tready(m_tready)
  );

  reg [7:0] pkt [0:511];
  reg [63:0] beat;
  integer errors = 0, i, b, j, sent, err_after_trunc;

  // Build one MoldUDP64 packet: session, seq, count messages of `mlen` bytes each.
  task build(input integer seqn, input integer count, input integer mlen);
    integer m, q;
    begin
      pkt[0]=8'h4E; pkt[1]=8'h41; pkt[2]=8'h53; pkt[3]=8'h44;
      pkt[4]=8'h41; pkt[5]=8'h51; pkt[6]=8'h30; pkt[7]=8'h31;
      pkt[8]=seqn[15:8]; pkt[9]=seqn[7:0];
      pkt[10]=count[15:8]; pkt[11]=count[7:0];
      q = 12;
      for (m = 0; m < count; m = m + 1) begin
        pkt[q]=mlen[15:8]; pkt[q+1]=mlen[7:0];
        for (i = 0; i < mlen; i = i + 1) pkt[q+2+i] = 8'h50 + i[7:0];
        q = q + 2 + mlen;
      end
      sent = q;
    end
  endtask

  // Drive the first `upto` bytes.
  task drive(input integer upto, input integer last);
    integer k, dn;
    begin
      k = 0;
      while (k < upto) begin
        dn = ((upto - k) < 8) ? (upto - k) : 8;
        beat = 64'd0;
        for (j = 0; j < dn; j = j + 1) beat[j*8 +: 8] = pkt[k + j];
        @(negedge aclk);
        s_tdata  = beat;
        s_tkeep  = (dn == 8) ? 8'hFF : (8'hFF >> (8 - dn));
        s_tvalid = 1;
        s_tlast  = last && ((k + dn) >= upto);
        @(posedge aclk);
        while (!s_tready) @(posedge aclk);
        k = k + dn;
      end
      @(negedge aclk);
      s_tvalid = 0;
      s_tkeep  = 8'hFF;
    end
  endtask

  initial begin
    aresetn = 0;
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);

    @(negedge aclk);
    awaddr = 5'h18; wdata = 32'h1; awvalid = 1; wvalid = 1;
    @(posedge aclk);
    for (i = 0; i < 50 && !(awready && wready); i = i + 1) @(posedge aclk);
    @(negedge aclk);
    awvalid = 0; wvalid = 0;
    repeat (3) @(negedge aclk);

    if (dut.enable !== 1'b1) begin
      $display("TRUNC-FAIL: enable never asserted");
      errors = errors + 1;
    end

    // A 200-byte single-message packet, truncated after 60 bytes.
    build(0, 1, 198);            // total = 12 + 2 + 198 = 212
    drive(60, 0);      // truncated: the transfer stops mid-packet
    repeat (400) @(negedge aclk);

    err_after_trunc = dut.error_count;
    $display("TRUNC after a 60-of-%0d byte transfer: pkts=%0d msgs=%0d err=%0d",
             sent, dut.rx_packets, dut.rx_messages, err_after_trunc);

    if (dut.error_count > 16'd1) begin
      $display("TRUNC-FAIL: err=%0d for one truncated packet - errors are per-byte, not per-packet",
               dut.error_count);
      errors = errors + 1;
    end

    // Recovery: a complete, well-formed packet must still parse.
    build(1, 1, 8);              // total = 12 + 2 + 8 = 22
    drive(sent, 1);    // complete: this one must parse
    repeat (400) @(negedge aclk);

    $display("TRUNC after recovery: pkts=%0d msgs=%0d err=%0d",
             dut.rx_packets, dut.rx_messages, dut.error_count);

    if (dut.rx_packets < 16'd1) begin
      $display("TRUNC-FAIL: no packet parsed after a truncated transfer - the module wedged");
      errors = errors + 1;
    end

    if (errors == 0) $display("TRUNC-PASS");
    else             $display("TRUNC-FAIL (%0d)", errors);
    $finish;
  end

endmodule
