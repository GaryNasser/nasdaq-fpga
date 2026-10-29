// tb_book: order_book end-to-end against the golden reference.
//
// order_book has only ever been verified ON HARDWARE. There is no simulation
// test for it at all, which means a change to itch_parse or to the book itself
// could silently alter the reconstructed book with nothing to catch it.
//
// This drives the real single-stock capture through
//
//     itch_parse -> order_book
//
// and compares every counter against the A9 software baseline
// (docs/measurements/baseline-a9.txt, stock_locate 6836):
//
//     add=15334 exe=7 can=12518 del=15291 rep=238 drop=12826 orders=320 levels=95
//
// itch_parse is fed the message stream directly (12-byte MoldUDP64 header
// stripped, 2-byte length prefix retained) so the test isolates the
// parse-to-book path rather than re-testing the reassembler.
`timescale 1ns / 1ps

module tb_book;

  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;

  // ---- itch_parse slave AXI-Lite -------------------------------------
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

  // ---- order_book slave AXI-Lite -------------------------------------
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

  // ---- itch_parse input stream ---------------------------------------
  reg  [63:0] s_axis_tdata = 0;
  reg  [7:0]  s_axis_tkeep = 8'hFF;
  reg         s_axis_tvalid = 0;
  wire        s_axis_tready;
  reg         s_axis_tlast = 0;

  // ---- parse -> book event bus ---------------------------------------
  wire [255:0] evt;
  wire         evt_valid;
  wire         evt_ready;
  wire [15:0]  stock_locate;
  wire         ts_in_valid;
  wire [63:0]  ts_in;

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
  parameter TOTAL_BYTES = 1237116;

  reg [7:0] img [0:MAXB-1];
  integer   pkt_off [0:NPKT-1];
  integer   pkt_len [0:NPKT-1];
  integer   k, p, off, cnt, m, mlen, q;
  reg [31:0] r_orders, r_levels, r_add, r_exe, r_can, r_del, r_rep, r_drop;
  integer total_msgs;
  integer idle;
  integer drain;
  initial begin idle = 0; drain = 0; end

  // Probe the pipeline: is the parser enabled and are events flowing?
  integer evt_count, msg_seen, tlast_seen, tl_driven, tl_taken, sent_bytes;
  initial begin tl_driven = 0; tl_taken = 0; sent_bytes = 0; end
  always @(posedge aclk) begin
    if (aresetn && s_axis_tvalid && s_axis_tlast) tl_driven = tl_driven + 1;
    if (aresetn && s_axis_tvalid && s_axis_tready) begin
      sent_bytes = sent_bytes + 1;
      if (s_axis_tlast) tl_taken = tl_taken + 1;
    end
  end
  initial begin evt_count = 0; msg_seen = 0; tlast_seen = 0; end
  always @(posedge aclk) if (aresetn && s_axis_tvalid && s_axis_tready && s_axis_tlast) tlast_seen = tlast_seen + 1;
  always @(posedge aclk) begin
    if (aresetn && evt_valid && evt_ready) evt_count = evt_count + 1;
  end
  // Where does the chain halt? Log the handshake at the 875th event.
  integer last_evt, halt_cyc, hcyc;
  initial begin last_evt = 0; halt_cyc = -1; hcyc = 0; end
  always @(posedge aclk) if (aresetn) hcyc = hcyc + 1;
  always @(posedge aclk) begin
    if (aresetn && evt_valid && evt_ready) last_evt = last_evt + 1;
    if (aresetn && halt_cyc < 0 && last_evt >= 875 && evt_valid && !evt_ready) begin
      halt_cyc = hcyc;
      $display("HALT cyc=%0d evt_valid=1 evt_ready=0 bk_busy=%b bk_state=%0d msg_latched=%b tready=%b",
               hcyc, bk.busy, bk.state, ip.msg_latched, s_axis_tready);
    end
  end
  // Compare the action the parser drives against the one the book latches,
  // for the first few events. Also log the first time each counter moves.
  integer seen_evt, seen_acc, last_add;
  initial begin seen_evt = 0; seen_acc = 0; last_add = 0; end
  always @(posedge aclk) begin
    if (aresetn && evt_valid && seen_evt < 6) begin
      $display("EVT act=%0d side=%b price=%0d shares=%0d ref=%0d ready=%b",
               ip.d_act, ip.d_side, ip.d_price, ip.d_shares, ip.d_order_ref,
               evt_ready);
      seen_evt = seen_evt + 1;
    end
    if (aresetn && evt_valid && evt_ready && seen_acc < 6) begin
      $display("  ACC bk_act=%0d bk_ev_act=%0d state=%0d", bk.act, bk.ev_act, bk.state);
      seen_acc = seen_acc + 1;
    end
    if (aresetn && bk.add_cnt != last_add) begin
      $display("ADDCNT %0d", bk.add_cnt);
      last_add = bk.add_cnt;
    end
  end
  // What is actually in msg_buf when the event is presented?
  integer mb_seen;
  initial mb_seen = 0;
  always @(posedge aclk) begin
    if (aresetn && evt_valid && mb_seen < 6) begin
      $display("MSGBUF b0=%02h b1=%02h b2=%02h b5=%02h lcnt=%0d act=%0d",
               ip.msg_buf[0], ip.msg_buf[1], ip.msg_buf[2], ip.msg_buf[5],
               ip.latched_cnt, ip.d_act);
      mb_seen = mb_seen + 1;
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
      bk_awaddr <= a;
      bk_awvalid <= 1; bk_wdata <= v; bk_wvalid <= 1;
      while (!(bk_awready && bk_wready)) @(negedge aclk);
      @(negedge aclk);
      bk_awvalid <= 0; bk_wvalid <= 0;
      while (!bk_bvalid) @(negedge aclk);
      @(negedge aclk);
    end
  endtask


  task bk_read(input [5:0] a, output [31:0] v);
    begin
      @(negedge aclk);
      bk_araddr <= a; bk_arvalid <= 1;
      while (!bk_arready) @(negedge aclk);
      @(negedge aclk);
      bk_arvalid <= 0;
      while (!bk_rvalid) @(posedge aclk);
      v = bk_rdata;
      @(negedge aclk);
    end
  endtask


  // Send the message stream: for each packet, the messages with their 2-byte
  // length prefixes, but WITHOUT the 12-byte MoldUDP64 header.

  task send_msgs;
    integer pp, c2, mm, ml2, base, qb, done, b;
    reg [63:0] wv;
    reg [7:0]  mbuf [0:1300000];
    reg        msg_last [0:1300000];
    integer nb;
    begin
      // Flatten every packet's messages into one byte buffer.
      nb = 0;
      for (pp = 0; pp < NPKT; pp = pp + 1) begin
        c2 = {img[pkt_off[pp]+10], img[pkt_off[pp]+11]};
        mm = pkt_off[pp] + 12;
        for (k = 0; k < c2; k = k + 1) begin
          ml2 = {img[mm], img[mm+1]};
          mbuf[nb] = img[mm];       msg_last[nb] = 1'b0; nb = nb + 1;
          mbuf[nb] = img[mm+1];     msg_last[nb] = 1'b0; nb = nb + 1;
          for (qb = 0; qb < ml2; qb = qb + 1) begin
            mbuf[nb] = img[mm + 2 + qb];
            msg_last[nb] = (qb == (ml2 - 1));
            nb = nb + 1;
          end
          mm = mm + 2 + ml2;
        end
      end
      total_msgs = nb;
      $display("MSGBYTES %0d", nb);

      // itch_parse consumes ONE BYTE PER BEAT from s_axis_tdata[7:0] -
      // exactly how mold64_reasm drives it (`assign m_axis_tdata =
      // {56'd0, out_byte}`). Packing 8 bytes into a beat made the parser
      // see only 1 byte in 8 and store garbage, so act was always 0.
      qb = 0;
      while (qb < nb) begin
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= {56'd0, mbuf[qb]};
        s_axis_tkeep  <= 8'h01;
        // TLAST on the final body byte of each MESSAGE.
        s_axis_tlast  <= msg_last[qb];
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        qb = qb + 1;
      end
      @(negedge aclk);
      s_axis_tvalid <= 0;
    end
  endtask

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

    // CTRL bit0 = 1 on both stages.
    ip_write(5'h14, 32'h1);
    bk_write(6'h30, 32'h1);
    repeat (4) @(negedge aclk);

    send_msgs;

    // Drain until the book has been idle for a sustained window.  A fixed
    // cycle count is wrong here: order_book searches the level table linearly
    // (up to 256 levels x 3 cycles per event that misses), so processing
    // 43428 events legitimately takes millions of cycles. Waiting on idleness
    // is both correct and usually faster.
    idle = 0;
    while (idle < 20000 && drain < 80000000) begin
      @(negedge aclk);
      drain = drain + 1;
      if (bk.busy || evt_valid || ip.msg_latched) idle = 0;
      else idle = idle + 1;
    end
    $display("DRAIN cycles=%0d idle_tail=%0d", drain, idle);

    $display("PROBE evt=%0d tlast=%0d bytes=%0d", evt_count, tl_taken, sent_bytes);
    bk_read(6'h00, r_orders);
    bk_read(6'h04, r_levels);
    bk_read(6'h18, r_add);
    bk_read(6'h1C, r_exe);
    bk_read(6'h20, r_can);
    bk_read(6'h24, r_del);
    bk_read(6'h28, r_rep);
    bk_read(6'h2C, r_drop);

    $display("BOOK add=%0d exe=%0d can=%0d del=%0d rep=%0d drop=%0d orders=%0d levels=%0d",
             r_add, r_exe, r_can, r_del, r_rep, r_drop, r_orders, r_levels);
    $display("GOLD add=15334 exe=7 can=12518 del=15291 rep=238 drop=12826 orders=320 levels=95");

    if (r_add == 32'd15334 && r_exe == 32'd7 && r_can == 32'd12518 &&
        r_del == 32'd15291 && r_rep == 32'd238 && r_drop == 32'd12826 &&
        r_orders == 32'd320 && r_levels == 32'd95)
      $display("BOOK-PASS");
    else
      $display("BOOK-FAIL");
    $finish;
  end

endmodule
