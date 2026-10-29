// tb_one_tlast2: independently written, to test whether tb_single_tlast's 8/850 is real.
//
// Deliberately structured differently from tb_single_tlast:
//   - the whole capture is loaded into one array and blitted out, with no per-packet bookkeeping
//   - tkeep is computed once, at the final beat, from `nbytes % 8`
//   - TLAST is asserted exactly once, on that beat, by a dedicated term
//   - the counters are SAMPLED after a long drain and reported with the TLAST count, so a bench that never
//     enabled the DUT cannot masquerade as a design result
//
// If this also gives 8/850, the observation stands. If it gives 850/850, tb_single_tlast is wrong and the last
// TLAST-related claim in this project falls.
`timescale 1ns / 1ps

module tb_one_tlast2;

  localparam integer NBYTES = 1237116;
  parameter integer  SEED       = 32'h1234_5678;
  localparam integer BEATS  = (NBYTES + 7) / 8;          // 154640 carries a 4-byte tail

  reg clk = 0, rstn = 0;
  always #2.5 clk = ~clk;

  reg  [4:0]  awaddr  = 0; reg awvalid = 0; wire awready;
  reg  [31:0] wdata   = 0; reg wvalid  = 0; wire wready;
  wire [1:0]  bresp;       wire bvalid;     reg  bready = 1;
  reg  [4:0]  araddr  = 0; reg arvalid = 0; wire arready;
  wire [31:0] rdata; wire [1:0] rresp; wire rvalid; reg rready = 1;

  reg  [63:0] tdata = 0; reg [7:0] tkeep = 8'hFF; reg tvalid = 0; reg tlast = 0;
  wire        tready;

  wire [63:0] md; wire [7:0] mk; wire mv; reg mr = 1;

  mold64_reasm #(.SESSION(64'h4E41534441513031)) dut (
    .aclk(clk), .aresetn(rstn),
    .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
    .s_axi_wdata(wdata), .s_axi_wstrb(5'h1F), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
    .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
    .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
    .s_axis_tdata(tdata), .s_axis_tkeep(tkeep), .s_axis_tvalid(tvalid), .s_axis_tready(tready),
    .s_axis_tlast(tlast),
    .m_axis_tdata(md), .m_axis_tkeep(mk), .m_axis_tvalid(mv), .m_axis_tready(mr)
  );

  reg [7:0] mem [0:NBYTES-1];
  integer b, j, sent;

  // Independent output accounting.
  reg [31:0] osum = 0;
  integer    ocnt = 0;
  always @(posedge clk)
    if (rstn && mv && mr) begin
      osum <= osum * 31 + {24'd0, md[7:0]};
      ocnt <= ocnt + 1;
    end

  // Expected: per message, 2 length bytes then payload.
  reg [31:0] xsum = 0;
  integer    xcnt = 0, xmsg = 0;
  integer    o, c, n, L;

  initial begin
    $readmemh("img.hex", mem);

    // Expected stream.
    o = 0;
    while (o + 12 <= NBYTES) begin
      c = {mem[o+10], mem[o+11]};
      o = o + 12;
      for (n = 0; n < c; n = n + 1) begin
        L = {mem[o], mem[o+1]};
        xsum = xsum * 31 + L[15:8];
        xsum = xsum * 31 + L[7:0];
        xcnt = xcnt + 2;
        for (j = 0; j < L; j = j + 1) begin
          xsum = xsum * 31 + mem[o+2+j];
          xcnt = xcnt + 1;
        end
        o = o + 2 + L;
        xmsg = xmsg + 1;
      end
    end
    $display("ONE2 expected msgs=%0d bytes=%0d sum=%08h", xmsg, xcnt, xsum);

    rstn = 0;
    repeat (8) @(negedge clk);
    rstn = 1;
    repeat (4) @(negedge clk);

    // Enable via CTRL = 1.
    @(negedge clk);
    awaddr = 5'h18; wdata = 32'h1; awvalid = 1; wvalid = 1;
    @(posedge clk);
    while (!(awready && wready)) @(posedge clk);
    @(negedge clk);
    awvalid = 0; wvalid = 0;
    repeat (4) @(negedge clk);

    if (dut.enable !== 1'b1) begin
      $display("ONE2-FAIL: enable never asserted (%b) - the DUT was never turned on", dut.enable);
      $finish;
    end

    // Blit: every beat, single TLAST on the last one.
    sent = 0;
    // xsim: seed the RNG through the standard system task.
    for (b = 0; b < BEATS; b = b + 1) begin
      @(negedge clk);
      for (j = 0; j < 8; j = j + 1)
        tdata[j*8 +: 8] = ((b*8 + j) < NBYTES) ? mem[b*8 + j] : 8'h00;
      if ((NBYTES - b*8) >= 8) tkeep = 8'hFF;
      else                     tkeep = 8'hFF >> (8 - (NBYTES - b*8));
      tvalid = 1;
      tlast  = (b == BEATS - 1);
      @(posedge clk);
      while (!tready) @(posedge clk);
      sent = sent + 1;
    end
    @(negedge clk);
    tvalid = 0; tlast = 0;

    repeat (12000) @(negedge clk);

    $display("ONE2 emitted  bytes=%0d sum=%08h", ocnt, osum);
    $display("ONE2 counters pkts=%0d msgs=%0d gap=%0d err=%0d tlast_seen=%0d beats_sent=%0d",
             dut.rx_packets, dut.rx_messages, dut.gap_count, dut.error_count,
             dut.dbg_tlast_cnt, sent);

    if (ocnt == xcnt && osum === xsum)
      $display("ONE2-PASS: a single TLAST still yields the exact message stream");
    else if (dut.rx_packets == 850)
      $display("ONE2-MOSTLY: 850 packets but %0d of %0d bytes emitted", ocnt, xcnt);
    else
      $display("ONE2-PARTIAL: %0d of 850 packets, %0d messages", dut.rx_packets, dut.rx_messages);

    $finish;
  end

endmodule
