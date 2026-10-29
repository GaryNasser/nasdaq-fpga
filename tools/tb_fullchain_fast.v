// tb_fullchain: the complete hardware datapath, which had never been tested.
//
// Every existing test exercises one boundary:
//
//   tb_realfile    mold64_reasm alone, real capture -> packet/message counts
//   tb_book        itch_parse -> order_book, fed a pre-split message stream
//   tb_rate_book   same, plus cycle accounting
//
// None of them chains the three modules the way the block design does:
//
//   DMA MM2S -> mold64_reasm -> itch_parse -> order_book
//               (m_axis)        (s_axis)      (evt bus)
//
// That chain has only ever run on hardware, and it is the configuration whose
// correctness the project actually claims. This drives the real capture into the
// reassembler and checks the book counters that come out the far end against the
// same golden reference tb_book uses.
//
// The inter-module wiring mirrors vivado/create_project.tcl: m_axis -> s_axis
// directly, evt/evt_valid/evt_ready/stock_locate between parse and book.
`timescale 1ns / 1ps

module tb_fullchain_fast;

  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;

  // ---- mold64_reasm AXI-Lite ------------------------------------------
  reg  [4:0]  m_awaddr = 0;
  reg         m_awvalid = 0;
  wire        m_awready;
  reg  [31:0] m_wdata = 0;
  reg         m_wvalid = 0;
  wire        m_wready;
  wire [1:0]  m_bresp;
  wire        m_bvalid;
  reg         m_bready = 1;
  reg  [4:0]  m_araddr = 0;
  reg         m_arvalid = 0;
  wire        m_arready;
  wire [31:0] m_rdata;
  wire [1:0]  m_rresp;
  wire        m_rvalid;
  reg         m_rready = 1;

  // ---- itch_parse AXI-Lite --------------------------------------------
  reg  [4:0]  p_awaddr = 0;
  reg         p_awvalid = 0;
  wire        p_awready;
  reg  [31:0] p_wdata = 0;
  reg         p_wvalid = 0;
  wire        p_wready;
  wire [1:0]  p_bresp;
  wire        p_bvalid;
  reg         p_bready = 1;
  reg  [4:0]  p_araddr = 0;
  reg         p_arvalid = 0;
  wire        p_arready;
  wire [31:0] p_rdata;
  wire [1:0]  p_rresp;
  wire        p_rvalid;
  reg         p_rready = 1;

  // ---- order_book AXI-Lite --------------------------------------------
  reg  [5:0]  b_awaddr = 0;
  reg         b_awvalid = 0;
  wire        b_awready;
  reg  [31:0] b_wdata = 0;
  reg         b_wvalid = 0;
  wire        b_wready;
  wire [1:0]  b_bresp;
  wire        b_bvalid;
  reg         b_bready = 1;
  reg  [5:0]  b_araddr = 0;
  reg         b_arvalid = 0;
  wire        b_arready;
  wire [31:0] b_rdata;
  wire [1:0]  b_rresp;
  wire        b_rvalid;
  reg         b_rready = 1;

  // ---- ts_hist AXI-Lite (12-bit address, 0x800 range) ------------------
  reg  [11:0] t_awaddr = 0;
  reg         t_awvalid = 0;
  wire        t_awready;
  reg  [31:0] t_wdata = 0;
  reg         t_wvalid = 0;
  wire        t_wready;
  wire [1:0]  t_bresp;
  wire        t_bvalid;
  reg         t_bready = 1;
  reg  [11:0] t_araddr = 0;
  reg         t_arvalid = 0;
  wire        t_arready;
  wire [31:0] t_rdata;
  wire [1:0]  t_rresp;
  wire        t_rvalid;
  reg         t_rready = 1;

  // ---- S_AXIS from the DMA --------------------------------------------
  reg  [63:0] s_axis_tdata = 0;
  reg  [7:0]  s_axis_tkeep = 8'hFF;
  reg         s_axis_tvalid = 0;
  wire        s_axis_tready;
  reg         s_axis_tlast = 0;

  // ---- mold64_reasm -> itch_parse -------------------------------------
  wire [63:0] mid_tdata;
  wire [7:0]  mid_tkeep;
  wire        mid_tvalid;
  wire        mid_tready;
  wire        mid_tlast;

  // ---- itch_parse -> order_book ---------------------------------------
  wire [255:0] evt;
  wire         evt_valid;
  wire         evt_ready;
  wire [15:0]  stock_locate;
  wire         ts_in_valid;

  // ==== the three modules, wired as in the block design ================
  mold64_reasm #(.SESSION(64'h4E41534441513031)) m64 (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(m_awaddr), .s_axi_awvalid(m_awvalid),
    .s_axi_awready(m_awready), .s_axi_wdata(m_wdata),
    .s_axi_wstrb(4'hF), .s_axi_wvalid(m_wvalid),
    .s_axi_wready(m_wready), .s_axi_bresp(m_bresp),
    .s_axi_bvalid(m_bvalid), .s_axi_bready(m_bready),
    .s_axi_araddr(m_araddr), .s_axi_arvalid(m_arvalid),
    .s_axi_arready(m_arready), .s_axi_rdata(m_rdata),
    .s_axi_rresp(m_rresp), .s_axi_rvalid(m_rvalid),
    .s_axi_rready(m_rready),
    .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(s_axis_tkeep),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tlast(s_axis_tlast),
    .m_axis_tdata(mid_tdata), .m_axis_tkeep(mid_tkeep),
    .m_axis_tvalid(mid_tvalid), .m_axis_tready(mid_tready),
    .m_axis_tlast(mid_tlast)
  );



  itch_parse ip (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(p_awaddr), .s_axi_awvalid(p_awvalid),
    .s_axi_awready(p_awready), .s_axi_wdata(p_wdata),
    .s_axi_wstrb(4'hF), .s_axi_wvalid(p_wvalid),
    .s_axi_wready(p_wready), .s_axi_bresp(p_bresp),
    .s_axi_bvalid(p_bvalid), .s_axi_bready(p_bready),
    .s_axi_araddr(p_araddr), .s_axi_arvalid(p_arvalid),
    .s_axi_arready(p_arready), .s_axi_rdata(p_rdata),
    .s_axi_rresp(p_rresp), .s_axi_rvalid(p_rvalid),
    .s_axi_rready(p_rready),
    .s_axis_tdata(mid_tdata), .s_axis_tkeep(mid_tkeep),
    .s_axis_tvalid(mid_tvalid), .s_axis_tready(mid_tready),
    .s_axis_tlast(mid_tlast),
    .evt(evt), .evt_valid(evt_valid), .evt_ready(evt_ready),
    .stock_locate(stock_locate),
    .ts_in_valid(ts_in_valid)
  );

  order_book bk (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(b_awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(b_awvalid),
    .s_axi_awready(b_awready), .s_axi_wdata(b_wdata),
    .s_axi_wstrb(4'hF), .s_axi_wvalid(b_wvalid),
    .s_axi_wready(b_wready), .s_axi_bresp(b_bresp),
    .s_axi_bvalid(b_bvalid), .s_axi_bready(b_bready),
    .s_axi_araddr(b_araddr), .s_axi_arprot(3'd0),
    .s_axi_arvalid(b_arvalid), .s_axi_arready(b_arready),
    .s_axi_rdata(b_rdata), .s_axi_rresp(b_rresp),
    .s_axi_rvalid(b_rvalid), .s_axi_rready(b_rready),
    .evt(evt), .evt_valid(evt_valid), .evt_ready(evt_ready),
    .stock_locate(stock_locate)
  );

  // ts_hist, wired as the block design does.  order_book's ST_BBO state
  // pulses ts_done_valid; itch_parse pulses ts_in_valid when it latches a
  // message; the act field rides along as msg_type (xlslice_act_0 in the BD).
  wire [3:0] evt_act = evt[3:0];

  ts_hist #() th (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(t_awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(t_awvalid),
    .s_axi_awready(t_awready), .s_axi_wdata(t_wdata),
    .s_axi_wstrb(4'hF), .s_axi_wvalid(t_wvalid),
    .s_axi_wready(t_wready), .s_axi_bresp(t_bresp),
    .s_axi_bvalid(t_bvalid), .s_axi_bready(t_bready),
    .s_axi_araddr(t_araddr), .s_axi_arprot(3'd0),
    .s_axi_arvalid(t_arvalid), .s_axi_arready(t_arready),
    .s_axi_rdata(t_rdata), .s_axi_rresp(t_rresp),
    .s_axi_rvalid(t_rvalid), .s_axi_rready(t_rready),
    .ingress_valid(ts_in_valid),
    .completion_valid(bk.ts_done_valid),
    .msg_type(evt_act)
  );

  parameter MAXB        = 1300000;
  parameter NPKT        = 850;
  parameter TOTAL_BYTES = 1237116;

  reg [7:0] img [0:MAXB-1];
  integer   pkt_off [0:NPKT-1];
  integer   pkt_len [0:NPKT-1];
  integer   k, p, off, cnt, m, mlen, q;

  // Expected results: identical to tb_book's golden reference.
  localparam EXP_ADD = 32'd15334;
  localparam EXP_EXE = 32'd7;
  localparam EXP_CAN = 32'd12518;
  localparam EXP_DEL = 32'd15291;
  localparam EXP_REP = 32'd238;
  localparam EXP_DROP= 32'd12826;
  localparam EXP_ORD = 32'd320;
  localparam EXP_LEV = 32'd95;

  integer tl_seen, beats_seen;
  initial begin tl_seen = 0; beats_seen = 0; end
  integer parse_beats;
  initial parse_beats = 0;
  always @(posedge aclk) begin
    if (aresetn && mid_tvalid && mid_tready) begin
      beats_seen = beats_seen + 1;
      if (mid_tlast) tl_seen = tl_seen + 1;
    end
    if (aresetn && mid_tvalid && mid_tready && !mid_tready) parse_beats = parse_beats + 1;
  end
  task m64_write(input [4:0] a, input [31:0] v);
    begin
      @(negedge aclk);
      m_awaddr <= a; m_awvalid <= 1; m_wdata <= v; m_wvalid <= 1;
      while (!(m_awready && m_wready)) @(negedge aclk);
      @(negedge aclk);
      m_awvalid <= 0; m_wvalid <= 0;
      while (!m_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  task ip_write(input [4:0] a, input [31:0] v);
    begin
      @(negedge aclk);
      p_awaddr <= a; p_awvalid <= 1; p_wdata <= v; p_wvalid <= 1;
      while (!(p_awready && p_wready)) @(negedge aclk);
      @(negedge aclk);
      p_awvalid <= 0; p_wvalid <= 0;
      while (!p_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  task bk_write(input [5:0] a, input [31:0] v);
    begin
      @(negedge aclk);
      b_awaddr <= a; b_awvalid <= 1; b_wdata <= v; b_wvalid <= 1;
      while (!(b_awready && b_wready)) @(negedge aclk);
      @(negedge aclk);
      b_awvalid <= 0; b_wvalid <= 0;
      while (!b_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  task bk_read(input [5:0] a, output [31:0] v);
    begin
      @(negedge aclk);
      b_araddr <= a; b_arvalid <= 1;
      while (!b_arready) @(negedge aclk);
      @(negedge aclk);
      b_arvalid <= 0;
      while (!b_rvalid) @(posedge aclk);
      v = b_rdata;
      @(negedge aclk);
    end
  endtask

  task th_write(input [11:0] a, input [31:0] v);
    begin
      @(negedge aclk);
      t_awaddr <= a; t_awvalid <= 1; t_wdata <= v; t_wvalid <= 1;
      while (!(t_awready && t_wready)) @(negedge aclk);
      @(negedge aclk);
      t_awvalid <= 0; t_wvalid <= 0;
      while (!t_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  task th_read(input [11:0] a, output [31:0] v);
    begin
      @(negedge aclk);
      t_araddr <= a; t_arvalid <= 1;
      while (!t_arready) @(negedge aclk);
      @(negedge aclk);
      t_arvalid <= 0;
      while (!t_rvalid) @(posedge aclk);
      v = t_rdata;
      @(negedge aclk);
    end
  endtask

  task send_pkt(input integer idx);
    integer done, base, len;
    reg [63:0] wv;
    begin
      base = pkt_off[idx];
      len  = pkt_len[idx];
      q = 0;
      while (q < len) begin
        done = (len - q) < 8 ? (len - q) : 8;
        for (k = 0; k < 8; k = k + 1)
          wv[k*8 +: 8] = (k < done) ? img[base + q + k] : 8'h00;
        // Fast producer: hold TVALID high and swap in the next beat on the
        // very cycle the previous one is accepted, with no idle gap. This is
        // what a DMA looks like to the module, and it is the condition under
        // which the reader can outrun the write-alignment stage.
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= wv;
        s_axis_tkeep  <= (done == 8) ? 8'hFF : ((8'hFF >> (8 - done)));
        s_axis_tlast  <= ((q + done) == len);
        q = q + done;
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
      end
    end
  endtask

  reg [31:0] r_add, r_exe, r_can, r_del, r_rep, r_drop, r_ord, r_lev;
  reg [63:0] t_bin_sum;
  reg [31:0] t_bin_tmp;
  integer bi;
  reg [31:0] t_h0, t_h1, t_h3, t_h4, t_h5;
  reg [31:0] t_ctrl, t_min, t_max, t_sum_lo, t_sum_hi, t_cnt_lo, t_cnt_hi;
  reg [63:0] t_count, t_sum;
  integer idle, drain;

  initial begin
    $readmemh("img.hex", img);

    off = 0;
    for (p = 0; p < NPKT; p = p + 1) begin
      pkt_off[p] = off;
      cnt = {img[off+10], img[off+11]};
      m = off + 12;
      for (k = 0; k < cnt; k = k + 1) begin
        mlen = {img[m], img[m+1]};
        m = m + 2 + mlen;
      end
      pkt_len[p] = m - off;
      off = m;
    end
    $display("SCAN packets=%0d consumed=%0d expected=%0d", NPKT, off, TOTAL_BYTES);
    // img.hex is reused across datasets, so a stale or wrong-sized image would
    // otherwise be interpreted as a design failure. Fail loudly with the real
    // reason instead.
    if (off != TOTAL_BYTES) begin
      $display("FULLCHAIN-FAIL: img.hex is %0d bytes but this test expects %0d - regenerate it with tools/run_realfile.py",
               off, TOTAL_BYTES);
      $finish;
    end

    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);

    // Soft-reset the FIFO then enable; enable the whole chain.
    m64_write(5'h18, 32'h3);
    ip_write(5'h14, 32'h1);
    bk_write(6'h30, 32'h1);
    th_write(12'h00, 32'h3);   // ts_hist: enable + clear stats
    repeat (8) @(negedge aclk);

    for (p = 0; p < NPKT; p = p + 1)
      send_pkt(p);

    @(negedge aclk);
    s_axis_tvalid <= 0;
    s_axis_tlast  <= 0;

    idle = 0; drain = 0;
    while (idle < 30000 && drain < 60000000) begin
      @(negedge aclk);
      drain = drain + 1;
      if (bk.busy || evt_valid || ip.msg_latched || m64.fifo_available != 0)
        idle = 0;
      else
        idle = idle + 1;
    end
    $display("DRAIN cycles=%0d mid_tlast=%0d beats=%0d parse_cnt=%0d", drain, tl_seen, beats_seen, ip.parse_cnt);

    bk_read(6'h00, r_ord);
    bk_read(6'h04, r_lev);
    bk_read(6'h18, r_add);
    bk_read(6'h1C, r_exe);
    bk_read(6'h20, r_can);
    bk_read(6'h24, r_del);
    bk_read(6'h28, r_rep);
    bk_read(6'h2C, r_drop);

    $display("CHAIN m64_pkts=%0d m64_msgs=%0d m64_gap=%0d m64_err=%0d parse=%0d",
             m64.rx_packets, m64.rx_messages, m64.gap_count, m64.error_count,
             ip.parse_cnt);
    $display("CHAIN book add=%0d exe=%0d can=%0d del=%0d rep=%0d drop=%0d orders=%0d levels=%0d",
             r_add, r_exe, r_can, r_del, r_rep, r_drop, r_ord, r_lev);
    $display("GOLD       add=%0d exe=%0d can=%0d del=%0d rep=%0d drop=%0d orders=%0d levels=%0d",
             EXP_ADD, EXP_EXE, EXP_CAN, EXP_DEL, EXP_REP, EXP_DROP, EXP_ORD, EXP_LEV);

    // ts_hist: the latency path was never exercised in the chain before.
    th_read(12'h00, t_ctrl);
    th_read(12'h18, t_min);
    th_read(12'h1C, t_max);
    th_read(12'h20, t_sum_lo);
    th_read(12'h24, t_sum_hi);
    th_read(12'h28, t_cnt_lo);
    th_read(12'h2C, t_cnt_hi);
    th_read(12'h30, t_h0);
    th_read(12'h34, t_h1);
    th_read(12'h3C, t_h3);
    th_read(12'h40, t_h4);
    th_read(12'h44, t_h5);
    $display("TSHIST bins: [0]=%0d [1]=%0d [3]=%0d [4]=%0d [5]=%0d",
             t_h0, t_h1, t_h3, t_h4, t_h5);
    // Dump every nonzero bin so the percentiles can be computed from real data
    // rather than a synthetic distribution.
    for (bi = 0; bi < 256; bi = bi + 1) begin
      th_read(12'h30 + 4 * bi, t_bin_tmp);
      if (t_bin_tmp != 0) $display("HISTBIN %0d %0d", bi, t_bin_tmp);
    end

    // Sum every histogram bin: it must equal count_delta, which is the
    // cheapest possible self-check that the histogram path is intact.
    t_bin_sum = 0;
    for (bi = 0; bi < 256; bi = bi + 1) begin
      th_read(12'h30 + 4 * bi, t_bin_tmp);
      t_bin_sum = t_bin_sum + t_bin_tmp;
    end
    $display("TSHBINS total_binned=%0d count=%0d %s",
             t_bin_sum, {t_cnt_hi, t_cnt_lo},
             (t_bin_sum == {t_cnt_hi, t_cnt_lo}) ? "CONSISTENT" : "MISMATCH");
    t_count = {t_cnt_hi, t_cnt_lo};
    t_sum   = {t_sum_hi, t_sum_lo};
    $display("TSH ctrl=%0d count=%0d min=%0d max=%0d sum=%0d mean=%0d",
             t_ctrl, t_count, t_min, t_max, t_sum,
             (t_count != 0) ? (t_sum / t_count) : 0);

    if (r_add == EXP_ADD && r_exe == EXP_EXE && r_can == EXP_CAN &&
        r_del == EXP_DEL && r_rep == EXP_REP && r_drop == EXP_DROP &&
        r_ord == EXP_ORD && r_lev == EXP_LEV &&
        m64.gap_count == 0 && m64.error_count == 0 &&
        t_count != 0 && t_bin_sum == t_count)
      $display("FULLCHAIN-PASS");
    else
      $display("FULLCHAIN-FAIL");
    $finish;
  end

endmodule
