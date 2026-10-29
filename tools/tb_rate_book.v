// tb_rate_book: measure the parse->book pipeline's throughput in cycles.
//
// The hardware measurement wraps clock_gettime() around a DMA transfer, so it
// includes DDR traffic, driver overhead and Python - none of which is the
// accelerator's own speed. With the board unavailable, the pipeline's intrinsic
// rate can still be measured exactly in simulation: count cycles from the first
// byte presented to the last event accepted, and divide by the message count.
//
// itch_parse accepts one byte per cycle. order_book processes an event in a
// variable number of cycles depending on how far its linear level search has to
// run. So the pipeline is throughput-limited by whichever is slower per message:
//   * the parser: (2 + body_len) cycles per message
//   * the book:  a serial FSM, up to LEVELS*3 cycles on a search miss
//
// This reports cycles/message, which converts to ns and to msg/s at the design
// clock, and shows where the time goes.
`timescale 1ns / 1ps

module tb_rate_book;

  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;          // 200 MHz period for the ratio only

  parameter CLK_NS = 5.263;          // 190 MHz design clock

  reg  [4:0]  ip_awaddr = 0;
  reg         ip_awvalid = 0;
  wire        ip_awready;
  reg  [31:0] ip_wdata = 0;
  reg         ip_wvalid = 0;
  wire        ip_wready;
  wire [1:0]  ip_bresp;
  wire        ip_bvalid;
  reg         ip_bready = 1;
  reg  [4:0]  ip_araddr = 0;
  reg         ip_arvalid = 0;
  wire        ip_arready;
  wire [31:0] ip_rdata;
  wire [1:0]  ip_rresp;
  wire        ip_rvalid;
  reg         ip_rready = 1;

  reg  [5:0]  bk_awaddr = 0;
  reg         bk_awvalid = 0;
  wire        bk_awready;
  reg  [31:0] bk_wdata = 0;
  reg         bk_wvalid = 0;
  wire        bk_wready;
  wire [1:0]  bk_bresp;
  wire        bk_bvalid;
  reg         bk_bready = 1;
  reg  [5:0]  bk_araddr = 0;
  reg         bk_arvalid = 0;
  wire        bk_arready;
  wire [31:0] bk_rdata;
  wire [1:0]  bk_rresp;
  wire        bk_rvalid;
  reg         bk_rready = 1;

  reg  [63:0] s_axis_tdata = 0;
  reg  [7:0]  s_axis_tkeep = 8'h01;
  reg         s_axis_tvalid = 0;
  wire        s_axis_tready;
  reg         s_axis_tlast = 0;

  wire [255:0] evt;
  wire         evt_valid;
  wire         evt_ready;
  wire [15:0]  stock_locate;
  wire         ts_in_valid;

  itch_parse ip (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(ip_awaddr), .s_axi_awvalid(ip_awvalid),
    .s_axi_awready(ip_awready), .s_axi_wdata(ip_wdata),
    .s_axi_wstrb(4'hF), .s_axi_wvalid(ip_wvalid),
    .s_axi_wready(ip_wready), .s_axi_bresp(ip_bresp),
    .s_axi_bvalid(ip_bvalid), .s_axi_bready(ip_bready),
    .s_axi_araddr(ip_araddr), .s_axi_arvalid(ip_arvalid),
    .s_axi_arready(ip_arready), .s_axi_rdata(ip_rdata),
    .s_axi_rresp(ip_rresp), .s_axi_rvalid(ip_rvalid),
    .s_axi_rready(ip_rready),
    .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(s_axis_tkeep),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tlast(s_axis_tlast),
    .evt(evt), .evt_valid(evt_valid), .evt_ready(evt_ready),
    .stock_locate(stock_locate),
    .ts_in_valid(ts_in_valid)
  );

  order_book bk (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(bk_awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(bk_awvalid),
    .s_axi_awready(bk_awready), .s_axi_wdata(bk_wdata),
    .s_axi_wstrb(4'hF), .s_axi_wvalid(bk_wvalid),
    .s_axi_wready(bk_wready), .s_axi_bresp(bk_bresp),
    .s_axi_bvalid(bk_bvalid), .s_axi_bready(bk_bready),
    .s_axi_araddr(bk_araddr), .s_axi_arprot(3'd0),
    .s_axi_arvalid(bk_arvalid), .s_axi_arready(bk_arready),
    .s_axi_rdata(bk_rdata), .s_axi_rresp(bk_rresp),
    .s_axi_rvalid(bk_rvalid), .s_axi_rready(bk_rready),
    .evt(evt), .evt_valid(evt_valid), .evt_ready(evt_ready),
    .stock_locate(stock_locate)
  );

  parameter MAXB        = 1300000;
  parameter NPKT        = 850;
  parameter NMSG        = 43428;
  parameter TOTAL_BYTES = 1237116;

  reg [7:0] img [0:MAXB-1];
  integer   pkt_off [0:NPKT-1];
  integer   pkt_len [0:NPKT-1];
  integer   k, p, off, cnt, m, mlen;

  // Measurement.
  integer cyc;
  integer first_take;
  integer last_evt;
  integer evt_count;
  integer max_busy_run, run_len;
  initial begin
    cyc = 0; first_take = -1; last_evt = -1; evt_count = 0;
    max_busy_run = 0; run_len = 0;
  end

  always @(posedge aclk) if (aresetn) cyc = cyc + 1;

  // Start the clock at the first byte actually accepted.
  always @(posedge aclk) begin
    if (aresetn && first_take < 0 && s_axis_tvalid && s_axis_tready)
      first_take = cyc;
  end

  always @(posedge aclk) begin
    if (aresetn && evt_valid && evt_ready) begin
      evt_count = evt_count + 1;
      last_evt  = cyc;
    end
  end

  // How long does the book hold the busiest single event?
  always @(posedge aclk) begin
    if (aresetn && bk.busy) begin
      run_len = run_len + 1;
      if (run_len > max_busy_run) max_busy_run = run_len;
    end else begin
      run_len = 0;
    end
  end

  // Where do the cycles actually go? Histogram the per-event busy length and
  // count how often the book enters the linear search.
  integer search_entries, ev_done, cur_len;
  integer h_short, h_med, h_long, h_huge;
  initial begin
    search_entries = 0; ev_done = 0; cur_len = 0;
    h_short = 0; h_med = 0; h_long = 0; h_huge = 0;
  end
  always @(posedge aclk) begin
    if (aresetn && bk.state == 4'd8) search_entries = search_entries + 1;
    if (aresetn && bk.busy) cur_len = cur_len + 1;
    if (aresetn && !bk.busy && cur_len > 0) begin
      if (cur_len <= 16) h_short = h_short + 1;
      else if (cur_len <= 64) h_med = h_med + 1;
      else if (cur_len <= 256) h_long = h_long + 1;
      else h_huge = h_huge + 1;
      ev_done = ev_done + 1;
      cur_len = 0;
    end
  end
  // Per-state cycle counts: this decides where an optimisation should go.
  integer sc0,sc1,sc2,sc3,sc4,sc5,sc6,sc7,sc8,sc9,sc10,sc11,sc12,sc13;
  initial begin
    sc0=0;sc1=0;sc2=0;sc3=0;sc4=0;sc5=0;sc6=0;
    sc7=0;sc8=0;sc9=0;sc10=0;sc11=0;sc12=0;sc13=0;
  end
  always @(posedge aclk) begin
    if (aresetn) begin
      case (bk.state)
        4'd0: sc0=sc0+1;
        4'd1: sc1=sc1+1;
        4'd2: sc2=sc2+1;
        4'd3: sc3=sc3+1;
        4'd4: sc4=sc4+1;
        4'd5: sc5=sc5+1;
        4'd6: sc6=sc6+1;
        4'd7: sc7=sc7+1;
        4'd8: sc8=sc8+1;
        4'd9: sc9=sc9+1;
        4'd10: sc10=sc10+1;
        4'd11: sc11=sc11+1;
        4'd12: sc12=sc12+1;
        4'd13: sc13=sc13+1;
        default: ;
      endcase
    end
  end

  task ip_write(input [4:0] a, input [31:0] v);
    begin
      @(negedge aclk);
      ip_awaddr <= a; ip_awvalid <= 1; ip_wdata <= v; ip_wvalid <= 1;
      while (!(ip_awready && ip_wready)) @(negedge aclk);
      @(negedge aclk);
      ip_awvalid <= 0; ip_wvalid <= 0;
      while (!ip_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  task bk_write(input [5:0] a, input [31:0] v);
    begin
      @(negedge aclk);
      bk_awaddr <= a; bk_awvalid <= 1; bk_wdata <= v; bk_wvalid <= 1;
      while (!(bk_awready && bk_wready)) @(negedge aclk);
      @(negedge aclk);
      bk_awvalid <= 0; bk_wvalid <= 0;
      while (!bk_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask

  // Byte-per-beat stream, TLAST on the final body byte of each message - the
  // same stimulus shape as tb_book, which now reproduces the golden counters.
  task send_msgs;
    integer pp, c2, mm, ml2, qb, nb;
    reg [7:0] mbuf [0:1300000];
    reg       mlast [0:1300000];
    begin
      nb = 0;
      for (pp = 0; pp < NPKT; pp = pp + 1) begin
        c2 = {img[pkt_off[pp]+10], img[pkt_off[pp]+11]};
        mm = pkt_off[pp] + 12;
        for (k = 0; k < c2; k = k + 1) begin
          ml2 = {img[mm], img[mm+1]};
          mbuf[nb] = img[mm];   mlast[nb] = 1'b0; nb = nb + 1;
          mbuf[nb] = img[mm+1]; mlast[nb] = 1'b0; nb = nb + 1;
          for (qb = 0; qb < ml2; qb = qb + 1) begin
            mbuf[nb] = img[mm + 2 + qb];
            mlast[nb] = (qb == (ml2 - 1));
            nb = nb + 1;
          end
          mm = mm + 2 + ml2;
        end
      end

      qb = 0;
      while (qb < nb) begin
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= {56'd0, mbuf[qb]};
        s_axis_tkeep  <= 8'h01;
        s_axis_tlast  <= mlast[qb];
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        qb = qb + 1;
      end
      @(negedge aclk);
      s_axis_tvalid <= 0;
      s_axis_tlast  <= 0;
    end
  endtask

  integer idle, drain;
  real cyc_per_msg, ns_per_msg, msg_per_s, mbps;

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

    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (4) @(negedge aclk);
    ip_write(5'h14, 32'h1);
    bk_write(6'h30, 32'h1);
    repeat (4) @(negedge aclk);

    send_msgs;

    idle = 0; drain = 0;
    while (idle < 20000 && drain < 80000000) begin
      @(negedge aclk);
      drain = drain + 1;
      if (bk.busy || evt_valid || ip.msg_latched) idle = 0;
      else idle = idle + 1;
    end

    if (last_evt > first_take && evt_count > 0) begin
      cyc_per_msg = (last_evt - first_take) * 1.0 / evt_count;
      ns_per_msg  = cyc_per_msg * CLK_NS;
      msg_per_s   = 1.0e9 / ns_per_msg;
      mbps        = msg_per_s * 28.0 / 1.0e6;
    end else begin
      cyc_per_msg = 0.0; ns_per_msg = 0.0; msg_per_s = 0.0; mbps = 0.0;
    end

    $display("RATE evt=%0d span_cycles=%0d cyc_per_msg=%0.3f ns_per_msg=%0.2f msg_per_s=%0.0f mb_per_s=%0.1f",
             evt_count, (last_evt - first_take), cyc_per_msg, ns_per_msg,
             msg_per_s, mbps);
    $display("RATE max_busy_run=%0d cycles (worst single event)", max_busy_run);
    $display("RATE events=%0d search_state_cycles=%0d  hist: <=16=%0d <=64=%0d <=256=%0d >256=%0d", ev_done, search_entries, h_short, h_med, h_long, h_huge);
    $display("STATECYC idle=%0d maprd=%0d mapwt=%0d levrd=%0d levwt=%0d levupd=%0d mapwr=%0d bbo=%0d search=%0d srchwt=%0d done=%0d srchchk=%0d mapchk=%0d levchk=%0d", sc0,sc1,sc2,sc3,sc4,sc5,sc6,sc7,sc8,sc9,sc10,sc11,sc12,sc13);
    $display("RATE counters add=%0d drop=%0d orders=%0d levels=%0d",
             bk.add_cnt, bk.drop_cnt, bk.order_cnt, bk.level_cnt);

    if (bk.add_cnt == 32'd15334 && bk.order_cnt == 32'd320 &&
        bk.level_cnt == 32'd95 && evt_count == NMSG)
      $display("RATE-PASS");
    else
      $display("RATE-FAIL");
    $finish;
  end

endmodule
