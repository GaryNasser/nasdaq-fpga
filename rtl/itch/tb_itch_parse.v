// tb_itch_parse: self-checking testbench for itch_parse.
//
// Checks:
//   1. after reset all stats registers read 0, CTRL reads 0
//   2. enable via CTRL.bit0 -> readback is 1
//   3. decode 'A' (Add Order, 36 bytes) -> evt fields match
//   4. decode 'X' (Cancel, 23 bytes) -> act=3
//   5. decode 'U' (Replace, 35 bytes) -> act=5, order_ref=old, aux_ref=new
//   6. decode 'R' (Directory, 39 bytes) -> act=7, STOCK_DIR_CNT=1
//   7. decode 'E' (Execute, 31 bytes) -> act=2
//   8. decode 'C' (Execute w/ Price, 36 bytes) -> act=2, aux_ref=match_id
//   9. length mismatch: 'A' with tlast at byte 20 -> DROP_LEN_CNT=1, no evt
//  10. unknown type 'Z' (10 bytes) -> act=0, ERR_TYPE_CNT=1, evt emitted
//  11. backpressure on evt: evt_ready=0, evt_valid holds, data stable
//  12. multiple messages A, X, D -> PARSE_CNT=3 cumulative
//  13. final stat check: PARSE_CNT, DROP_LEN_CNT, ERR_TYPE_CNT, STOCK_DIR_CNT

`timescale 1ns / 1ps

module tb_itch_parse;

  // Clock / reset
  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;   // 200 MHz functional test clock

  // AXI4-Lite
  reg  [4:0]  awaddr = 0;
  reg  [2:0]  awprot = 0;
  reg         awvalid = 0;
  wire        awready;
  reg  [31:0] wdata = 0;
  reg  [3:0]  wstrb = 4'b1111;
  reg         wvalid = 0;
  wire        wready;
  wire [1:0]  bresp;
  wire        bvalid;
  reg         bready = 1;
  reg  [4:0]  araddr = 0;
  reg  [2:0]  arprot = 0;
  reg         arvalid = 0;
  wire        arready;
  wire [31:0] rdata;
  wire [1:0]  rresp;
  wire        rvalid;
  reg         rready = 1;

  // AXI-Stream slave (TB drives, DUT receives)
  reg  [63:0] s_tdata = 0;
  reg  [7:0]  s_tkeep = 8'h01;
  reg         s_tvalid = 0;
  wire        s_tready;
  reg         s_tlast = 0;

  // Decoded event output (DUT drives, TB receives)
  wire [255:0] evt;
  wire         evt_valid;
  reg          evt_ready = 0;

  itch_parse dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(awaddr), .s_axi_awprot(awprot),
    .s_axi_awvalid(awvalid), .s_axi_awready(awready),
    .s_axi_wdata(wdata), .s_axi_wstrb(wstrb),
    .s_axi_wvalid(wvalid), .s_axi_wready(wready),
    .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
    .s_axi_araddr(araddr), .s_axi_arprot(arprot),
    .s_axi_arvalid(arvalid), .s_axi_arready(arready),
    .s_axi_rdata(rdata), .s_axi_rresp(rresp),
    .s_axi_rvalid(rvalid), .s_axi_rready(rready),

    .s_axis_tdata(s_tdata), .s_axis_tkeep(s_tkeep),
    .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready),
    .s_axis_tlast(s_tlast),

    .evt(evt), .evt_valid(evt_valid), .evt_ready(evt_ready)
  );

  // ----------------------------------------------------------------------
  integer errors = 0;

  // Declarations used by tasks and stimulus
  reg [31:0] v0, v1, v2;
  reg [7:0]  msg_buf [0:63];
  integer    i;

  task check(input cond, input [511:0] name);
    begin
      if (cond) $display("[PASS] %0s", name);
      else begin $display("[FAIL] %0s", name); errors = errors + 1; end
    end
  endtask

  // AXI-Lite write (RREADY/BREADY tied high).
  task axi_write(input [4:0] addr, input [31:0] data);
    begin
      @(negedge aclk);
      awaddr  <= addr;
      awvalid <= 1;
      wdata   <= data;
      wstrb   <= 4'b1111;
      wvalid  <= 1;
      // Wait for the write handshake at posedge.
      begin : whs
        reg wdone;
        wdone = 0;
        while (!wdone) begin
          @(posedge aclk);
          if (awready && wready) begin
            wdone = 1;
            awvalid <= 0;
            wvalid  <= 0;
          end
        end
      end
      // Wait for the write response (bvalid) to come and go.
      while (!bvalid) @(posedge aclk);
      @(posedge aclk);  // bready is tied high; b_valid clears next cycle
      @(negedge aclk);
    end
  endtask

  // AXI-Lite read (RREADY tied high).
  task axi_read(input [4:0] addr, output [31:0] data);
    begin
      @(negedge aclk);
      araddr  <= addr;
      arvalid <= 1;
      @(negedge aclk);
      while (!rvalid) @(negedge aclk);
      data = rdata;
      arvalid <= 0;
      @(negedge aclk);
    end
  endtask

  // Drive one S_AXIS beat (one byte) and wait for the handshake at posedge.
  task s_send(input [7:0] b, input last);
    begin
      @(negedge aclk);
      s_tdata  <= {56'd0, b};
      s_tkeep  <= 8'h01;
      s_tvalid <= 1;
      s_tlast  <= last;
      begin : hs
        reg sdone;
        sdone = 0;
        while (!sdone) begin
          @(posedge aclk);
          if (s_tvalid && s_tready) begin
            sdone = 1;
            s_tvalid <= 0;
            s_tlast  <= 0;
          end
        end
      end
      @(negedge aclk);
    end
  endtask

  // Send a whole message: msg_buf[0..len-1], tlast on the last byte.
  // A 2-byte big-endian length prefix is sent first, matching what
  // mold64_reasm actually puts on M_AXIS ({len_hi, len_lo, body...}, TLAST on
  // the last body byte).  The parser discards the prefix.  Driving the prefix
  // here keeps the TB faithful to the real interface — without it every
  // message decoded as type 0x00 on hardware while this TB still passed.
  task send_msg(input integer len);
    begin
      s_send(8'd0, 1'b0);                        // length[15:8]
      s_send(len[7:0], 1'b0);                    // length[7:0]
      for (i = 0; i < len; i = i + 1) begin
        s_send(msg_buf[i], (i == len - 1) ? 1'b1 : 1'b0);
      end
    end
  endtask

  // Wait for evt_valid, compare evt to expected, pulse evt_ready to consume.
  task recv_event(input [255:0] expected, input [511:0] name);
    begin
      @(negedge aclk);
      while (!evt_valid) @(negedge aclk);
      $display("    [DBG] evt=%0h expected=%0h", evt, expected);
      check(evt == expected, name);
      evt_ready <= 1;
      @(posedge aclk);   // consume happens at this posedge
      @(negedge aclk);
      evt_ready <= 0;
    end
  endtask

  // ----------------------------------------------------------------------
  // Stimulus
  // ----------------------------------------------------------------------
  initial begin
    // ----- reset -----
    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);

    // -- 1. reset values --
    axi_read(5'h00, v0); check(v0 == 32'd0, "rset PARSE_CNT_LO");
    axi_read(5'h04, v0); check(v0 == 32'd0, "rset PARSE_CNT_HI");
    axi_read(5'h08, v0); check(v0 == 32'd0, "rset DROP_LEN_CNT");
    axi_read(5'h0C, v0); check(v0 == 32'd0, "rset ERR_TYPE_CNT");
    axi_read(5'h10, v0); check(v0 == 32'd0, "rset STOCK_DIR_CNT");
    axi_read(5'h14, v0); check(v0 == 32'd0, "rset CTRL");

    // -- 2. enable --
    axi_write(5'h14, 32'h1);
    axi_read(5'h14, v0); check(v0 == 32'd1, "CTRL readback == 1");

    // -- 3. decode 'A' (Add Order, 36 bytes) --
    // Common header: type, stock_locate=0x0001, tracking=0, timestamp
    msg_buf[0]  = 8'h41;                 // 'A'
    msg_buf[1]  = 8'h00; msg_buf[2]  = 8'h01;  // stock_locate
    msg_buf[3]  = 8'h00; msg_buf[4]  = 8'h00;  // tracking
    msg_buf[5]  = 8'h00; msg_buf[6]  = 8'h00; msg_buf[7]  = 8'h00;  // timestamp
    msg_buf[8]  = 8'h00; msg_buf[9]  = 8'h27; msg_buf[10] = 8'h10;  // =10000
    // Type-specific: order_ref=100, side='B', shares=100, stock, price=1502500
    msg_buf[11] = 8'h00; msg_buf[12] = 8'h00; msg_buf[13] = 8'h00; msg_buf[14] = 8'h00;
    msg_buf[15] = 8'h00; msg_buf[16] = 8'h00; msg_buf[17] = 8'h00; msg_buf[18] = 8'h64; // ref=100
    msg_buf[19] = 8'h42;                          // side 'B' (buy)
    msg_buf[20] = 8'h00; msg_buf[21] = 8'h00; msg_buf[22] = 8'h00; msg_buf[23] = 8'h64; // shares=100
    msg_buf[24] = 8'h41; msg_buf[25] = 8'h41; msg_buf[26] = 8'h50; msg_buf[27] = 8'h4C; // "AAPL"
    msg_buf[28] = 8'h20; msg_buf[29] = 8'h20; msg_buf[30] = 8'h20; msg_buf[31] = 8'h20; // "    "
    msg_buf[32] = 8'h00; msg_buf[33] = 8'h16; msg_buf[34] = 8'hED; msg_buf[35] = 8'h24; // price=1502500
    send_msg(36);
    // Expected event (struct layout per fixed RTL):
    //   [255:253]=0, [252:245]=type, [244:197]=timestamp, [196:133]=order_ref,
    //   [132:69]=aux_ref, [68:37]=price, [36:5]=shares, [4]=side, [3:0]=act
    recv_event({3'd0, 8'h41, 48'h000000002710, 64'h0000000000000064,
                64'd0, 32'h0016ED24, 32'h00000064, 1'b0, 4'd1},
               "decode A: evt fields");
    axi_read(5'h00, v0); check(v0 == 32'd1, "PARSE_CNT_LO == 1 after A");

    // -- 4. decode 'X' (Cancel, 23 bytes) --
    msg_buf[0]  = 8'h58;                          // 'X'
    msg_buf[1]  = 8'h00; msg_buf[2]  = 8'h02;     // stock_locate
    msg_buf[3]  = 8'h00; msg_buf[4]  = 8'h00;     // tracking
    msg_buf[5]  = 8'h00; msg_buf[6]  = 8'h00; msg_buf[7]  = 8'h00;  // timestamp
    msg_buf[8]  = 8'h00; msg_buf[9]  = 8'h4E; msg_buf[10] = 8'h20;  // =20000
    msg_buf[11] = 8'h00; msg_buf[12] = 8'h00; msg_buf[13] = 8'h00; msg_buf[14] = 8'h00;
    msg_buf[15] = 8'h00; msg_buf[16] = 8'h00; msg_buf[17] = 8'h00; msg_buf[18] = 8'hC8; // ref=200
    msg_buf[19] = 8'h00; msg_buf[20] = 8'h00; msg_buf[21] = 8'h00; msg_buf[22] = 8'h32; // shares=50
    send_msg(23);
    recv_event({3'd0, 8'h58, 48'h000000004E20, 64'h00000000000000C8,
                64'd0, 32'd0, 32'h00000032, 1'b0, 4'd3},
               "decode X: evt fields (act=cancel)");
    axi_read(5'h08, v0); check(v0 == 32'd0, "DROP_LEN_CNT == 0 after X");

    // -- 5. decode 'U' (Replace, 35 bytes) --
    msg_buf[0]  = 8'h55;                          // 'U'
    msg_buf[1]  = 8'h00; msg_buf[2]  = 8'h03;     // stock_locate
    msg_buf[3]  = 8'h00; msg_buf[4]  = 8'h00;     // tracking
    msg_buf[5]  = 8'h00; msg_buf[6]  = 8'h00; msg_buf[7]  = 8'h00;  // timestamp
    msg_buf[8]  = 8'h00; msg_buf[9]  = 8'h75; msg_buf[10] = 8'h30;  // =30000
    msg_buf[11] = 8'h00; msg_buf[12] = 8'h00; msg_buf[13] = 8'h00; msg_buf[14] = 8'h00;
    msg_buf[15] = 8'h00; msg_buf[16] = 8'h00; msg_buf[17] = 8'h00; msg_buf[18] = 8'h64; // old=100
    msg_buf[19] = 8'h00; msg_buf[20] = 8'h00; msg_buf[21] = 8'h00; msg_buf[22] = 8'h00;
    msg_buf[23] = 8'h00; msg_buf[24] = 8'h00; msg_buf[25] = 8'h00; msg_buf[26] = 8'hC8; // new=200
    msg_buf[27] = 8'h00; msg_buf[28] = 8'h00; msg_buf[29] = 8'h00; msg_buf[30] = 8'h64; // shares=100
    msg_buf[31] = 8'h00; msg_buf[32] = 8'h00; msg_buf[33] = 8'h00; msg_buf[34] = 8'h64; // price=100
    send_msg(35);
    // order_ref = old (100), aux_ref = new (200), act=replace(5)
    recv_event({3'd0, 8'h55, 48'h000000007530, 64'h0000000000000064,
                64'h00000000000000C8, 32'h00000064, 32'h00000064, 1'b0, 4'd5},
               "decode U: evt fields (act=replace)");

    // -- 6. decode 'R' (Directory, 39 bytes) --
    msg_buf[0]  = 8'h52;                          // 'R'
    msg_buf[1]  = 8'h00; msg_buf[2]  = 8'h04;     // stock_locate
    msg_buf[3]  = 8'h00; msg_buf[4]  = 8'h00;     // tracking
    msg_buf[5]  = 8'h00; msg_buf[6]  = 8'h00; msg_buf[7]  = 8'h00;  // timestamp
    msg_buf[8]  = 8'h00; msg_buf[9]  = 8'h9C; msg_buf[10] = 8'h40;  // =40000
    for (i = 11; i < 39; i = i + 1) msg_buf[i] = 8'h00;
    send_msg(39);
    // Directory: order_ref=0, aux_ref=0, act=directory(7)
    recv_event({3'd0, 8'h52, 48'h000000009C40, 64'd0,
                64'd0, 32'd0, 32'd0, 1'b0, 4'd7},
               "decode R: evt fields (act=directory)");
    axi_read(5'h10, v0); check(v0 == 32'd1, "STOCK_DIR_CNT == 1 after R");

    // -- 7. decode 'E' (Execute, 31 bytes) --
    msg_buf[0]  = 8'h45;                          // 'E'
    msg_buf[1]  = 8'h00; msg_buf[2]  = 8'h05;     // stock_locate
    msg_buf[3]  = 8'h00; msg_buf[4]  = 8'h00;     // tracking
    msg_buf[5]  = 8'h00; msg_buf[6]  = 8'h00; msg_buf[7]  = 8'h00;  // timestamp
    msg_buf[8]  = 8'h00; msg_buf[9]  = 8'hC3; msg_buf[10] = 8'h50;  // =50000
    msg_buf[11] = 8'h00; msg_buf[12] = 8'h00; msg_buf[13] = 8'h00; msg_buf[14] = 8'h00;
    msg_buf[15] = 8'h00; msg_buf[16] = 8'h00; msg_buf[17] = 8'h01; msg_buf[18] = 8'hF4; // ref=500
    msg_buf[19] = 8'h00; msg_buf[20] = 8'h00; msg_buf[21] = 8'h00; msg_buf[22] = 8'h64; // shares=100
    for (i = 23; i < 31; i = i + 1) msg_buf[i] = 8'h00;
    send_msg(31);
    recv_event({3'd0, 8'h45, 48'h00000000C350, 64'h00000000000001F4,
                64'd0, 32'd0, 32'h00000064, 1'b0, 4'd2},
               "decode E: evt fields (act=execute)");

    // -- 8. decode 'C' (Execute w/ Price, 36 bytes) --
    msg_buf[0]  = 8'h43;                          // 'C'
    msg_buf[1]  = 8'h00; msg_buf[2]  = 8'h06;     // stock_locate
    msg_buf[3]  = 8'h00; msg_buf[4]  = 8'h00;     // tracking
    msg_buf[5]  = 8'h00; msg_buf[6]  = 8'h00; msg_buf[7]  = 8'h00;  // timestamp
    msg_buf[8]  = 8'h00; msg_buf[9]  = 8'h27; msg_buf[10] = 8'h10;  // =10000
    msg_buf[11] = 8'h00; msg_buf[12] = 8'h00; msg_buf[13] = 8'h00; msg_buf[14] = 8'h00;
    msg_buf[15] = 8'h00; msg_buf[16] = 8'h00; msg_buf[17] = 8'h00; msg_buf[18] = 8'h2C; // ref=600? 0x2C=44
    // Use ref=600 = 0x258
    msg_buf[11] = 8'h00; msg_buf[12] = 8'h00; msg_buf[13] = 8'h00; msg_buf[14] = 8'h00;
    msg_buf[15] = 8'h00; msg_buf[16] = 8'h00; msg_buf[17] = 8'h02; msg_buf[18] = 8'h58; // ref=600
    msg_buf[19] = 8'h00; msg_buf[20] = 8'h00; msg_buf[21] = 8'h00; msg_buf[22] = 8'h64; // shares=100
    msg_buf[23] = 8'h00; msg_buf[24] = 8'h00; msg_buf[25] = 8'h00; msg_buf[26] = 8'h64; // price=100
    msg_buf[27] = 8'h00; msg_buf[28] = 8'h00; msg_buf[29] = 8'h00; msg_buf[30] = 8'h00;
    msg_buf[31] = 8'h00; msg_buf[32] = 8'h00; msg_buf[33] = 8'h00; msg_buf[34] = 8'h01; // match_id=1
    msg_buf[35] = 8'h00;                          // padding to 36 bytes
    send_msg(36);
    // C: act=execute(2), aux_ref=match_id(1)
    recv_event({3'd0, 8'h43, 48'h000000002710, 64'h0000000000000258,
                64'h0000000000000001, 32'h00000064, 32'h00000064, 1'b0, 4'd2},
               "decode C: evt fields (act=execute, aux=match)");

    // -- 9. length mismatch: 'A' with tlast at byte 20 (not 36) --
    for (i = 0; i < 20; i = i + 1) msg_buf[i] = 8'h41;  // fill with 'A'
    send_msg(20);
    // Message is dropped: no evt_valid, DROP_LEN_CNT increments.
    // Wait a few cycles for the drop to register, then check.
    repeat (4) @(negedge aclk);
    check(evt_valid == 1'b0, "length mismatch: no evt_valid");
    axi_read(5'h08, v0); check(v0 == 32'd1, "DROP_LEN_CNT == 1 after len mismatch");

    // -- 10. unknown type 'Z' (0x5A), 11 bytes --
    // Send 11 bytes so the timestamp field (bytes[5:10]) is fully
    // overwritten; otherwise byte[10] is stale from the previous message.
    for (i = 0; i < 11; i = i + 1) msg_buf[i] = 8'h5A;
    send_msg(11);
    // Unknown type: accepted at any length, act=unknown(0), ERR_TYPE_CNT++,
    // evt still emitted with msg_type=0x5A.
    // Timestamp reads msg_buf[5..10]; all 11 bytes are 0x5A here, so the
    // full timestamp is 48'h5A5A5A5A5A5A.
    recv_event({3'd0, 8'h5A, 48'h5A5A5A5A5A5A, 64'd0,
                64'd0, 32'd0, 32'd0, 1'b0, 4'd0},
               "decode Z: evt fields (act=unknown)");
    axi_read(5'h0C, v0); check(v0 == 32'd1, "ERR_TYPE_CNT == 1 after Z");

    // -- 11. backpressure on evt --
    // evt_ready is 0 by default. Send a message, verify evt_valid holds.
    msg_buf[0]  = 8'h41;                          // 'A'
    msg_buf[1]  = 8'h00; msg_buf[2]  = 8'h07;     // stock_locate
    msg_buf[3]  = 8'h00; msg_buf[4]  = 8'h00;     // tracking
    msg_buf[5]  = 8'h00; msg_buf[6]  = 8'h00; msg_buf[7]  = 8'h00;  // timestamp
    msg_buf[8]  = 8'h00; msg_buf[9]  = 8'h10; msg_buf[10] = 8'h00;  // =4096
    msg_buf[11] = 8'h00; msg_buf[12] = 8'h00; msg_buf[13] = 8'h00; msg_buf[14] = 8'h00;
    msg_buf[15] = 8'h00; msg_buf[16] = 8'h00; msg_buf[17] = 8'h00; msg_buf[18] = 8'h01; // ref=1
    msg_buf[19] = 8'h53;                          // side 'S' (sell)
    msg_buf[20] = 8'h00; msg_buf[21] = 8'h00; msg_buf[22] = 8'h00; msg_buf[23] = 8'h01; // shares=1
    for (i = 24; i < 36; i = i + 1) msg_buf[i] = 8'h00;
    send_msg(36);
    // Wait for evt_valid
    @(negedge aclk);
    while (!evt_valid) @(negedge aclk);
    // evt_ready is 0: evt_valid should hold and data should be stable.
    begin : bp_sample
      reg [255:0] samp1, samp2;
      samp1 = evt;
      repeat (3) @(negedge aclk);
      check(evt_valid == 1'b1, "backpressure: evt_valid holds");
      samp2 = evt;
      check(samp1 == samp2, "backpressure: evt data stable");
    end
    // Now release and capture.
    check(evt_valid == 1'b1, "backpressure: evt_valid still high before ready");
    recv_event({3'd0, 8'h41, 48'h000000001000, 64'h0000000000000001,
                64'd0, 32'd0, 32'h00000001, 1'b1, 4'd1},
               "backpressure: evt after release");

    // -- 12. multiple messages sequentially: A, then X, then D --
    // 'A' message
    msg_buf[0]  = 8'h41;
    msg_buf[1]  = 8'h00; msg_buf[2]  = 8'h08;
    msg_buf[3]  = 8'h00; msg_buf[4]  = 8'h00;
    msg_buf[5]  = 8'h00; msg_buf[6]  = 8'h00; msg_buf[7]  = 8'h00;
    msg_buf[8]  = 8'h00; msg_buf[9]  = 8'h00; msg_buf[10] = 8'h01;  // ts=1
    msg_buf[11] = 8'h00; msg_buf[12] = 8'h00; msg_buf[13] = 8'h00; msg_buf[14] = 8'h00;
    msg_buf[15] = 8'h00; msg_buf[16] = 8'h00; msg_buf[17] = 8'h00; msg_buf[18] = 8'h01; // ref=1
    msg_buf[19] = 8'h42;                          // 'B'
    msg_buf[20] = 8'h00; msg_buf[21] = 8'h00; msg_buf[22] = 8'h00; msg_buf[23] = 8'h01; // shares=1
    for (i = 24; i < 36; i = i + 1) msg_buf[i] = 8'h00;
    send_msg(36);
    recv_event({3'd0, 8'h41, 48'h000000000001, 64'h0000000000000001,
                64'd0, 32'd0, 32'h00000001, 1'b0, 4'd1},
               "multi: decode A");

    // 'X' message
    msg_buf[0]  = 8'h58;
    msg_buf[1]  = 8'h00; msg_buf[2]  = 8'h09;
    msg_buf[3]  = 8'h00; msg_buf[4]  = 8'h00;
    msg_buf[5]  = 8'h00; msg_buf[6]  = 8'h00; msg_buf[7]  = 8'h00;
    msg_buf[8]  = 8'h00; msg_buf[9]  = 8'h00; msg_buf[10] = 8'h02;  // ts=2
    msg_buf[11] = 8'h00; msg_buf[12] = 8'h00; msg_buf[13] = 8'h00; msg_buf[14] = 8'h00;
    msg_buf[15] = 8'h00; msg_buf[16] = 8'h00; msg_buf[17] = 8'h00; msg_buf[18] = 8'h02; // ref=2
    msg_buf[19] = 8'h00; msg_buf[20] = 8'h00; msg_buf[21] = 8'h00; msg_buf[22] = 8'h02; // shares=2
    send_msg(23);
    recv_event({3'd0, 8'h58, 48'h000000000002, 64'h0000000000000002,
                64'd0, 32'd0, 32'h00000002, 1'b0, 4'd3},
               "multi: decode X");

    // 'D' message (Delete, 19 bytes)
    msg_buf[0]  = 8'h44;
    msg_buf[1]  = 8'h00; msg_buf[2]  = 8'h0A;
    msg_buf[3]  = 8'h00; msg_buf[4]  = 8'h00;
    msg_buf[5]  = 8'h00; msg_buf[6]  = 8'h00; msg_buf[7]  = 8'h00;
    msg_buf[8]  = 8'h00; msg_buf[9]  = 8'h00; msg_buf[10] = 8'h03;  // ts=3
    msg_buf[11] = 8'h00; msg_buf[12] = 8'h00; msg_buf[13] = 8'h00; msg_buf[14] = 8'h00;
    msg_buf[15] = 8'h00; msg_buf[16] = 8'h00; msg_buf[17] = 8'h00; msg_buf[18] = 8'h03; // ref=3
    send_msg(19);
    recv_event({3'd0, 8'h44, 48'h000000000003, 64'h0000000000000003,
                64'd0, 32'd0, 32'd0, 1'b0, 4'd4},
               "multi: decode D");

    // Cumulative PARSE_CNT: A + X + U + R + E + C + Z + bp_A + multi_A + multi_X + multi_D = 11
    axi_read(5'h00, v0); axi_read(5'h04, v1);
    check(v0 == 32'd11, "PARSE_CNT_LO == 11 total");
    check(v1 == 32'd0,  "PARSE_CNT_HI == 0 total");

    // -- 13. final stat check --
    axi_read(5'h08, v0); check(v0 == 32'd1, "final DROP_LEN_CNT == 1");
    axi_read(5'h0C, v0); check(v0 == 32'd1, "final ERR_TYPE_CNT == 1");
    axi_read(5'h10, v0); check(v0 == 32'd1, "final STOCK_DIR_CNT == 1");

    if (errors == 0) begin
      $display("TB-ALL-PASS");
      $finish;
    end else begin
      $display("TB-FAILED %0d error(s)", errors);
      $finish;
    end
  end

endmodule
