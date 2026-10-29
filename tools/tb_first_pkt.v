// tb_first_pkt: drive ONE packet through the whole chain and report the BOOK counters.
//
// Round 136 measured on hardware: a single 49-message packet gives messages=49, add=0, drop=0.
// The reassembler delivers; the book sees nothing. tb_fullchain replays all 850 packets, so a
// first-packet loss is invisible there - 15334 is checked after 850 packets, and a missing 8 at the
// start looks like noise.
//
// This drives the first packet only and prints what the BOOK counted, which is the number that
// decides whether the defect reproduces in simulation at all.
`timescale 1ns / 1ps

module tb_first_pkt;

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

  // reassembler input
  reg  [63:0] s_tdata = 0;
  reg  [7:0]  s_tkeep = 8'hFF;
  reg         s_tvalid = 0;
  wire        s_tready;
  reg         s_tlast = 0;

  // reassembler -> parser
  wire [63:0] m64_data;
  wire        m64_valid;
  wire        m64_ready;

  // parser -> book
  wire [7:0]  evt;
  wire        evt_valid;
  wire        evt_ready;
  wire [15:0] stock_locate;
  wire        book_ready;

  wire [7:0]  ip_out_data;
  wire        ip_out_valid;

  // ---- reassembler ----
  mold64_reasm #(.SESSION(64'h4E41534441513031)) reasm (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
    .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
    .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
    .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
    .s_axis_tdata(s_tdata), .s_axis_tkeep(s_tkeep), .s_axis_tvalid(s_tvalid),
    .s_axis_tready(s_tready), .s_axis_tlast(s_tlast),
    .m_axis_tdata(m64_data), .m_axis_tvalid(m64_valid), .m_axis_tready(m64_ready)
  );

  // ---- parser ----
  itch_parse iparse (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid), .s_axi_awready(),
    .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(),
    .s_axi_bresp(), .s_axi_bvalid(), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arvalid(arvalid), .s_axi_arready(),
    .s_axi_rdata(), .s_axi_rresp(), .s_axi_rvalid(), .s_axi_rready(rready),
    .s_axis_tdata(m64_data), .s_axis_tvalid(m64_valid), .s_axis_tready(m64_ready),
    .evt(evt), .evt_valid(evt_valid), .evt_ready(evt_ready),
    .stock_locate(stock_locate),
    .m_axis_tdata(ip_out_data), .m_axis_tvalid(ip_out_valid), .m_axis_tready(book_ready)
  );

  // ---- book ----
  order_book obook (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid), .s_axi_awready(),
    .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(),
    .s_axi_bresp(), .s_axi_bvalid(), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arvalid(arvalid), .s_axi_arready(),
    .s_axi_rdata(), .s_axi_rresp(), .s_axi_rvalid(), .s_axi_rready(rready),
    .evt(evt), .evt_valid(evt_valid), .evt_ready(evt_ready),
    .stock_locate(stock_locate),
    .s_axis_tdata(ip_out_data), .s_axis_tvalid(ip_out_valid), .s_axis_tready(book_ready)
  );

  initial begin
    repeat (6) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    repeat (500) @(negedge aclk);
    $display("FP reassembler: pkts=%0d msgs=%0d err=%0d gap=%0d",
             reasm.rx_packets, reasm.rx_messages, reasm.error_count, reasm.gap_count);
    $display("FP book      : add=%0d del=%0d drop=%0d orders=%0d levels=%0d",
             obook.add_cnt, obook.del_cnt, obook.drop_cnt, obook.order_cnt, obook.level_cnt);
    if (reasm.rx_messages > 0 && obook.add_cnt == 0)
      $display("FP-DIAG-FAIL-REPRODUCED: messages delivered, no Adds counted");
    else if (reasm.rx_messages == 0)
      $display("FP-DIAG-NO-INPUT: the reassembler delivered nothing");
    else
      $display("FP-DIAG-ADDS-COUNTED add=%0d", obook.add_cnt);
    $finish;
  end

endmodule
