// tb_fullchain_1m: the whole reassembler -> parser chain on the 29 MB capture.
//
// tb_realfile already proves mold64_reasm handles all 1,000,000 messages of
// itch_1m.mold64, but it stops at the reassembler boundary. The full chain has
// only ever been run on the 1.2 MB single-stock capture, which wraps the 4096-
// byte ring ~300 times; this one wraps it ~7000 times and exercises every
// backpressure pattern the parser can generate over 20042 packets.
//
// The order book is NOT compared here: itch_1m spans 8714 distinct stock
// locates and order_book maintains a single-stock book by design, so a golden
// answer is not meaningful. What IS checked is what the chain must preserve
// regardless of the book: every packet, every message, zero gaps, zero errors.
`timescale 1ns / 1ps

module tb_fullchain_1m;

  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;

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

  reg  [63:0] s_axis_tdata = 0;
  reg  [7:0]  s_axis_tkeep = 8'hFF;
  reg         s_axis_tvalid = 0;
  wire        s_axis_tready;
  reg         s_axis_tlast = 0;

  wire [63:0] mid_tdata;
  wire [7:0]  mid_tkeep;
  wire        mid_tvalid;
  wire        mid_tready;
  wire        mid_tlast;

  wire [255:0] evt;
  wire         evt_valid;
  wire         evt_ready;
  wire [15:0]  stock_locate;
  wire         ts_in_valid;

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

  // The parser must apply its REAL backpressure, so it is driven with events
  // consumed at a realistic rate by a simple ready model - the order book is
  // single-stock and would stall forever on 8714 locates.
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

  // Event sink: ready except for EVT_STALL cycles after each accepted event,
  // which reproduces the parser's msg_latched stall faithfully enough to
  // exercise inter-module backpressure at scale.
  parameter EVT_STALL = 40;
  reg [15:0] evt_gap;
  reg        evt_hold;
  initial begin evt_gap = 0; evt_hold = 0; end
  always @(posedge aclk) begin
    if (!aresetn) begin evt_hold <= 1'b0; evt_gap <= 0; end
    else if (evt_hold) begin
      if (evt_gap == 0) evt_hold <= 1'b0;
      else evt_gap <= evt_gap - 1;
    end else if (evt_valid && evt_ready) begin
      evt_hold <= 1'b1;
      evt_gap  <= EVT_STALL;
    end
  end
  assign evt_ready = aresetn && !evt_hold;

  parameter MAXB = 29300000;
  parameter NPKT = 20042;

  reg [7:0]  img [0:MAXB-1];
  integer    pkt_off [0:NPKT-1];
  integer    pkt_len [0:NPKT-1];
  integer    k, p, off, cnt, m, mlen, q;

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
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= wv;
        s_axis_tkeep  <= (done == 8) ? 8'hFF : ((8'hFF >> (8 - done)));
        s_axis_tlast  <= ((q + done) == len);
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        q = q + done;
      end
    end
  endtask

  integer idle;

  initial begin
    $readmemh("img1m.hex", img);

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
    $display("SCAN packets=%0d consumed=%0d", NPKT, off);
    if (off != 29204943) begin
      $display("CHAIN1M-FAIL: img1m.hex is %0d bytes but this test expects 29204943 - regenerate with tools/run_realfile.py 1m",
               off);
      $finish;
    end

    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    m64_write(5'h18, 32'h3);
    ip_write(5'h14, 32'h1);
    repeat (8) @(negedge aclk);

    for (p = 0; p < NPKT; p = p + 1)
      send_pkt(p);

    @(negedge aclk);
    s_axis_tvalid <= 0;
    s_axis_tlast  <= 0;

    idle = 0;
    while (idle < 50000) begin
      @(negedge aclk);
      if (m64.fifo_available != 0 || evt_valid || ip.msg_latched)
        idle = 0;
      else
        idle = idle + 1;
    end

    $display("CHAIN1M m64_pkts=%0d m64_msgs=%0d gap=%0d err=%0d parse=%0d",
             m64.rx_packets, m64.rx_messages, m64.gap_count, m64.error_count,
             ip.parse_cnt);

    if (m64.rx_packets == 20042 && m64.rx_messages == 1000000 &&
        m64.gap_count == 0 && m64.error_count == 0 &&
        ip.parse_cnt == 1000000)
      $display("CHAIN1M-PASS");
    else
      $display("CHAIN1M-FAIL");
    $finish;
  end

endmodule
