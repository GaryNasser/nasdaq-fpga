// itch_parse: ITCH 5.0 protocol parser for Nasdaq market-data feed.
//
// Parses a byte-stream of ITCH 5.0 messages (one byte per AXI-Stream beat,
// TLAST delimits each message) and emits fully-decoded book events on a
// wide single-beat struct interface.
//
// ITCH 5.0 message types handled (fixed-length per type, big-endian fields):
//   'A' (0x41) Add Order (no MPID)        len 36
//   'F' (0x46) Add Order (with MPID)      len 40
//   'E' (0x45) Order Executed             len 31
//   'C' (0x43) Order Executed With Price   len 36
//   'X' (0x58) Order Cancel               len 23
//   'D' (0x44) Order Delete               len 19
//   'U' (0x55) Order Replace              len 35
//   'R' (0x52) Stock Directory            len 39
//
// All multi-byte integers are big-endian per the ITCH 5.0 spec.  Timestamps
// are 48 bits (6 bytes), order references are 64 bits (8 bytes).
//
// ----------------------------------------------------------------------
// Output struct (flat 256-bit wire; bit-select packing, no typedef)
// ----------------------------------------------------------------------
//   [255:253] rsvd          — 3 bits, reserved (zero)
//   [252:245] msg_type      — 8 bits, original ITCH type byte
//   [244:197] timestamp     — 48 bits, nanoseconds since midnight
//   [196:133] order_ref     — 64 bits, order reference number
//                           For Replace this is the OLD reference.
//   [132: 69] aux_ref       — 64 bits, auxiliary reference
//                           For Replace: NEW reference.
//                           For Execute-With-Price: match ID (zero-extended).
//                           Otherwise zero.
//   [ 68: 37] price         — 32 bits, ITCH fixed-point (4 implied decimals)
//   [ 36:  5] shares        — 32 bits
//   [  9:  9] side          — 1 bit, 0=Buy ('B'), 1=Sell ('S')
//   [  8:  0] act           — 9 bits, encoded action (see ACT_* below)
//
// Note: stock_locate (the symbol index) is passed via order_ref's upper bits
// in downstream modules; here it is stored in the lower 16 bits of aux_ref
// for directory messages and is otherwise available to the consumer via the
// raw message buffer if needed.  For all order messages stock_locate is the
// 16-bit value at bytes [1:2]; it is not duplicated in the struct.
//
// Action encoding (act field):
//   4'd0  ACT_UNKNOWN    unrecognised type byte (still forwarded)
//   4'd1  ACT_ADD        Add Order ('A' / 'F')
//   4'd2  ACT_EXECUTE    Order Executed ('E') / With Price ('C')
//   4'd3  ACT_CANCEL     Order Cancel ('X')
//   4'd4  ACT_DELETE     Order Delete ('D')
//   4'd5  ACT_REPLACE    Order Replace ('U')
//   4'd6  ACT_TRADE      (reserved for future trade messages)
//   4'd7  ACT_DIRECTORY  Stock Directory ('R')
//
// ----------------------------------------------------------------------
// AXI4-Lite register map (RW ctrl, RO stats)
// ----------------------------------------------------------------------
//   0x00 PARSE_CNT_LO   RO  lower 32 bits of parsed-message count
//   0x04 PARSE_CNT_HI   RO  upper 32 bits
//   0x08 DROP_LEN_CNT   RO  messages dropped (length mismatch / truncated)
//   0x0C ERR_TYPE_CNT   RO  messages with unknown type byte
//   0x10 STOCK_DIR_CNT  RO  Stock Directory ('R') messages decoded
//   0x14 CTRL           RW  bit0=enable (default 0); [31:1] reserved
//
// Addressing: 5-bit araddr/awaddr; register selected by araddr[4:2] (word
// index), matching the ctrl_regs.v / loopback_dma.v decoder convention.

`timescale 1ns / 1ps

module itch_parse (
    input  wire        aclk,
    input  wire        aresetn,

    // AXI4-Lite slave (stats + control)
    input  wire [4:0]  s_axi_awaddr,
    input  wire [2:0]  s_axi_awprot,
    input  wire        s_axi_awvalid,
    output wire        s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output wire        s_axi_wready,
    output wire [1:0]  s_axi_bresp,
    output wire        s_axi_bvalid,
    input  wire        s_axi_bready,
    input  wire [4:0]  s_axi_araddr,
    input  wire [2:0]  s_axi_arprot,
    input  wire        s_axi_arvalid,
    output wire        s_axi_arready,
    output wire [31:0] s_axi_rdata,
    output wire [1:0]  s_axi_rresp,
    output wire        s_axi_rvalid,
    input  wire        s_axi_rready,

    // AXI-Stream slave: raw ITCH messages IN (1 byte per beat)
    input  wire [63:0] s_axis_tdata,
    input  wire [7:0]  s_axis_tkeep,
    input  wire        s_axis_tvalid,
    output wire        s_axis_tready,
    input  wire        s_axis_tlast,

    // Decoded book event OUT (single-beat wide struct, valid/ready handshake)
    output wire [255:0] evt,
    output wire         evt_valid,
    input  wire         evt_ready,

    // Stock locate (symbol index) for the current message — needed by the
    // order book (M4) to route events to the correct stock.  Valid whenever
    // evt_valid is high.  Extracted from bytes [1:2] of every ITCH message.
    output wire [15:0]  stock_locate,

    // Sideband: pulses for one cycle when a decoded event is first presented
    // on the output (evt_valid rises).  Used by ts_hist (M5) to capture the
    // ingress timestamp t0.
    output wire         ts_in_valid
);

  // ----------------------------------------------------------------------
  // ITCH 5.0 message type codes (ASCII)
  // ----------------------------------------------------------------------
  localparam [7:0] ITCH_TYPE_ADD       = 8'h41; // 'A'
  localparam [7:0] ITCH_TYPE_ADD_MPID  = 8'h46; // 'F'
  localparam [7:0] ITCH_TYPE_EXEC      = 8'h45; // 'E'
  localparam [7:0] ITCH_TYPE_EXEC_PRICE= 8'h43; // 'C'
  localparam [7:0] ITCH_TYPE_CANCEL    = 8'h58; // 'X'
  localparam [7:0] ITCH_TYPE_DELETE    = 8'h44; // 'D'
  localparam [7:0] ITCH_TYPE_REPLACE   = 8'h55; // 'U'
  localparam [7:0] ITCH_TYPE_DIR       = 8'h52; // 'R'

  // Expected byte length per type (including the 1-byte type field)
  localparam [7:0] LEN_ADD       = 8'd36;
  localparam [7:0] LEN_ADD_MPID  = 8'd40;
  localparam [7:0] LEN_EXEC      = 8'd31;
  localparam [7:0] LEN_EXEC_PRICE= 8'd36;
  localparam [7:0] LEN_CANCEL    = 8'd23;
  localparam [7:0] LEN_DELETE    = 8'd19;
  localparam [7:0] LEN_REPLACE   = 8'd35;
  localparam [7:0] LEN_DIR       = 8'd39;

  // Action encoding for the act field
  localparam [3:0] ACT_UNKNOWN   = 4'd0;
  localparam [3:0] ACT_ADD       = 4'd1;
  localparam [3:0] ACT_EXECUTE   = 4'd2;
  localparam [3:0] ACT_CANCEL    = 4'd3;
  localparam [3:0] ACT_DELETE    = 4'd4;
  localparam [3:0] ACT_REPLACE   = 4'd5;
  localparam [3:0] ACT_TRADE     = 4'd6;
  localparam [3:0] ACT_DIRECTORY = 4'd7;

  // Message buffer depth (max ITCH message is 40 bytes; 50 is safe headroom)
  localparam BUF_DEPTH = 6'd50;

  // ----------------------------------------------------------------------
  // AXI4-Lite register address decode
  // ----------------------------------------------------------------------
  localparam ADDR_PARSE_CNT_LO  = 3'd0; // 0x00
  localparam ADDR_PARSE_CNT_HI  = 3'd1; // 0x04
  localparam ADDR_DROP_LEN_CNT  = 3'd2; // 0x08
  localparam ADDR_ERR_TYPE_CNT  = 3'd3; // 0x0C
  localparam ADDR_STOCK_DIR_CNT = 3'd4; // 0x10
  localparam ADDR_CTRL          = 3'd5; // 0x14

  // ----------------------------------------------------------------------
  // Forward-declared control register (declared early because the byte
  // collector and decode logic reference `enable` combinationally; the
  // AXI-Lite write logic that drives ctrl_en lives further below).
  // ----------------------------------------------------------------------
  reg  ctrl_en;
  wire enable = ctrl_en;

  // Registered length-valid flag.  It used to be combinational from
  // latched_cnt (the length compare plus type decode fed the drop counter
  // enables and the collector's discard mux; post-route WNS -0.311 ns).
  // It is now computed from the byte being committed and stored when the
  // message is latched, so consumers see a plain flop.
  reg len_ok_r;
  reg len_ok_next;   // combinational next value, assigned further below

  // ----------------------------------------------------------------------
  // Byte collector: shift incoming bytes into the message buffer
  // ----------------------------------------------------------------------
  reg [7:0] msg_buf [0:BUF_DEPTH-1];
  reg [7:0] msg_cnt;       // number of bytes collected in current message
  reg       msg_latched;   // buffer holds a complete message; decode pending
  reg [1:0] pref_skip;     // 2-byte length-prefix bytes left to discard

  wire s_axis_handshake = s_axis_tvalid && s_axis_tready;

  // S_AXIS TREADY: accept bytes while we are enabled and not holding a
  // latched message for decode (we must drain the message before accepting
  // the next one).
  assign s_axis_tready = enable && !msg_latched;

  // Input capture register.  Writing msg_buf straight from s_axis_tdata put
  // the mold64_reasm -> itch_parse net on the critical path: one source
  // flop drives ~85 msg_buf data pins, which routed in 4.75 ns with zero
  // logic levels (WNS -0.321 ns).  Capturing the byte in a local register
  // first moves the fan-out net inside this module; the collector commits
  // the captured byte on the following cycle.  Steady state still accepts
  // one byte per cycle (commit of byte N overlaps capture of byte N+1).
  reg [7:0] in_byte_r;
  reg       in_last_r;
  reg       in_valid_r;

  // Load the latched buffer on the last byte of a message (or any byte if
  // the message is truncated — we still latch and let decode handle it).
  reg [7:0] latched_cnt;

  always @(posedge aclk) begin
    if (!aresetn) begin
      msg_cnt    <= 8'd0;
      msg_latched<= 1'b0;
      latched_cnt<= 8'd0;
      in_byte_r  <= 8'd0;
      in_last_r  <= 1'b0;
      in_valid_r <= 1'b0;
      len_ok_r   <= 1'b1;
      pref_skip  <= 2'd2;   // every message arrives with a 2-byte length prefix
    end else if (enable) begin
      // ------------------------------------------------------------------
      // Length-prefix alignment.
      //
      // mold64_reasm delimits each message on M_AXIS as
      //     { 2-byte big-endian length, body... }  with TLAST on the last
      // body byte (see its ST_EMIT_LEN_HI / ST_EMIT_LEN_LO states).
      // This parser, however, consumes messages as { 1-byte type, ... } and
      // derives the type from msg_buf[0].  Without skipping the prefix every
      // message's "type" byte is the length MSB (0x00), so every message
      // landed in the ACT_UNKNOWN branch: on hardware the counters read
      // parse_cnt == err_type_cnt with zero book events.
      //
      // pref_skip counts the prefix bytes still to discard at the start of
      // each message.  Alignment is re-established whenever TLAST or an idle
      // gap leaves the module out of message context.
      // ------------------------------------------------------------------
      // Commit the previously captured byte.  While msg_latched is high the
      // buffer is being decoded; hold the captured byte (TREADY is low, so
      // no further byte can arrive) and commit it after the latch clears.
      if (in_valid_r && !msg_latched) begin
        if (pref_skip != 2'd0) begin
          // Discard the 2-byte length prefix; it is redundant with the
          // message length that the type byte plus ITCH rules already give.
          pref_skip <= pref_skip - 2'd1;
        end else begin
          msg_buf[msg_cnt] <= in_byte_r;
          if (in_last_r) begin
            // Message is complete — latch the count and mark for decode.
            // The length check is registered here from the type byte and the
            // final count (for a one-byte message the type is the byte being
            // committed, not msg_buf[0]).
            latched_cnt <= msg_cnt + 8'd1;
            msg_latched <= 1'b1;
            msg_cnt     <= 8'd0;
            len_ok_r    <= len_ok_next;
            pref_skip   <= 2'd2;   // next message starts with a length prefix
          end else begin
            msg_cnt <= msg_cnt + 8'd1;
          end
        end
      end else if (msg_latched && evt_valid && evt_ready) begin
        // The latched message has been consumed on the output; clear the
        // latch so the next bytes can be collected.
        msg_latched <= 1'b0;
      end else if (msg_latched && !len_ok_r) begin
        // Length mismatch: discard the message (no event was presented) and
        // clear the latch so the next bytes can be collected.
        msg_latched <= 1'b0;
      end

      // Capture the next stream byte (overlaps the commit above).
      if (s_axis_handshake) begin
        in_byte_r  <= s_axis_tdata[7:0];
        in_last_r  <= s_axis_tlast;
        in_valid_r <= 1'b1;
      end else if (in_valid_r && !msg_latched) begin
        // The captured byte was committed; the register is free again.
        in_valid_r <= 1'b0;
      end
    end
  end

  // ----------------------------------------------------------------------
  // Combinational decode: extract fields from the latched buffer
  // ----------------------------------------------------------------------
  // Common fields (present in every ITCH message type):
  //   msg_buf[0]          type byte
  //   msg_buf[1:2]        stock_locate  (16 bits BE)
  //   msg_buf[3:4]        tracking_number (16 bits BE)
  //   msg_buf[5:12]       timestamp (48 bits BE, bytes 5..10 — 6 bytes)
  //
  // NOTE: ITCH timestamp is 6 bytes (48 bits) at bytes [5:10].  Bytes 11:12
  // are NOT part of the timestamp.  Re-read the spec: ITCH 5.0 common header
  // is stock_locate[2], tracking_number[2], timestamp[6] = bytes 0..10 but
  // byte 0 is the type.  So after the type byte: [1:2] locate, [3:4] track,
  // [5:10] timestamp.  That is 11 bytes total before type-specific fields.

  wire [7:0]  d_type      = msg_buf[0];
  wire [15:0] d_locate    = {msg_buf[1], msg_buf[2]};
  wire [47:0] d_timestamp = {msg_buf[5], msg_buf[6], msg_buf[7], msg_buf[8],
                            msg_buf[9], msg_buf[10]};

  // Type-specific fields (combinational extraction per type).
  // For type 'A' (len 36):
  //   order_ref  [13:20] 8 bytes
  //   side       [21]    1 byte  ('B'/'S')
  //   shares     [22:25] 4 bytes
  //   stock      [26:33] 8 bytes
  //   price      [34:37] 4 bytes
  wire [63:0] d_ref_add       = {msg_buf[11], msg_buf[12], msg_buf[13], msg_buf[14],
                                msg_buf[15], msg_buf[16], msg_buf[17], msg_buf[18]};
  wire [7:0]  d_side_add      = msg_buf[19];
  wire [31:0] d_shares_add    = {msg_buf[20], msg_buf[21], msg_buf[22], msg_buf[23]};
  wire [31:0] d_price_add     = {msg_buf[32], msg_buf[33], msg_buf[34], msg_buf[35]};

  // For type 'F' (len 40): same as A but mpid at [34:37], price at [38:41]
  wire [63:0] d_ref_add_mpid  = d_ref_add;
  wire [7:0]  d_side_add_mpid = d_side_add;
  wire [31:0] d_shares_add_mpid = d_shares_add;
  wire [31:0] d_price_add_mpid  = {msg_buf[36], msg_buf[37], msg_buf[38], msg_buf[39]};

  // For type 'E' (len 31):
  //   order_ref  [13:20]
  //   shares     [21:24]  (executed shares)
  wire [63:0] d_ref_exec      = d_ref_add;
  wire [31:0] d_shares_exec   = {msg_buf[19], msg_buf[20], msg_buf[21], msg_buf[22]};

  // For type 'C' (len 36):
  //   order_ref  [13:20]
  //   shares     [21:24]  (executed shares)
  //   price      [25:28]
  //   match_id   [29:36]  (8 bytes)
  wire [63:0] d_ref_exec_price = d_ref_add;
  wire [31:0] d_shares_exec_price = d_shares_exec;
  wire [31:0] d_price_exec_price  = {msg_buf[23], msg_buf[24], msg_buf[25], msg_buf[26]};
  wire [63:0] d_match_id         = {msg_buf[27], msg_buf[28], msg_buf[29], msg_buf[30],
                                    msg_buf[31], msg_buf[32], msg_buf[33], msg_buf[34]};

  // For type 'X' (len 23):
  //   order_ref  [13:20]
  //   shares     [21:24]  (cancelled shares)
  wire [63:0] d_ref_cancel     = d_ref_add;
  wire [31:0] d_shares_cancel  = d_shares_exec;

  // For type 'D' (len 19):
  //   order_ref  [13:20]
  wire [63:0] d_ref_delete     = d_ref_add;

  // For type 'U' (len 35):
  //   old_ref    [13:20]
  //   new_ref    [21:28]
  //   shares     [29:32]
  //   price      [33:36]
  wire [63:0] d_old_ref        = d_ref_add;
  wire [63:0] d_new_ref        = {msg_buf[19], msg_buf[20], msg_buf[21], msg_buf[22],
                                 msg_buf[23], msg_buf[24], msg_buf[25], msg_buf[26]};
  wire [31:0] d_shares_replace = {msg_buf[27], msg_buf[28], msg_buf[29], msg_buf[30]};
  wire [31:0] d_price_replace  = {msg_buf[31], msg_buf[32], msg_buf[33], msg_buf[34]};

  // For type 'R' (len 39): stock directory — no order_ref.  We set act=7
  // and pass stock_locate + timestamp.  aux_ref is zero.

  // ----------------------------------------------------------------------
  // Combinational action + field mux (selected by type byte)
  // ----------------------------------------------------------------------
  reg [3:0]  d_act;
  reg [63:0] d_order_ref;
  reg [63:0] d_aux_ref;
  reg [31:0] d_price;
  reg [31:0] d_shares;
  reg        d_side;       // 0=Buy, 1=Sell

  always @(*) begin
    // Defaults
    d_act       = ACT_UNKNOWN;
    d_order_ref = 64'd0;
    d_aux_ref   = 64'd0;
    d_price     = 32'd0;
    d_shares    = 32'd0;
    d_side      = 1'b0;

    case (d_type)
      ITCH_TYPE_ADD: begin
        d_act       = ACT_ADD;
        d_order_ref = d_ref_add;
        d_price     = d_price_add;
        d_shares    = d_shares_add;
        d_side      = (d_side_add == 8'h53); // 'S' -> 1 (sell)
      end
      ITCH_TYPE_ADD_MPID: begin
        d_act       = ACT_ADD;
        d_order_ref = d_ref_add_mpid;
        d_price     = d_price_add_mpid;
        d_shares    = d_shares_add_mpid;
        d_side      = (d_side_add_mpid == 8'h53);
      end
      ITCH_TYPE_EXEC: begin
        d_act       = ACT_EXECUTE;
        d_order_ref = d_ref_exec;
        d_shares    = d_shares_exec;
      end
      ITCH_TYPE_EXEC_PRICE: begin
        d_act       = ACT_EXECUTE;
        d_order_ref = d_ref_exec_price;
        d_price     = d_price_exec_price;
        d_shares    = d_shares_exec_price;
        d_aux_ref   = d_match_id;
      end
      ITCH_TYPE_CANCEL: begin
        d_act       = ACT_CANCEL;
        d_order_ref = d_ref_cancel;
        d_shares    = d_shares_cancel;
      end
      ITCH_TYPE_DELETE: begin
        d_act       = ACT_DELETE;
        d_order_ref = d_ref_delete;
      end
      ITCH_TYPE_REPLACE: begin
        d_act       = ACT_REPLACE;
        d_order_ref = d_old_ref;
        d_aux_ref   = d_new_ref;
        d_price     = d_price_replace;
        d_shares    = d_shares_replace;
      end
      ITCH_TYPE_DIR: begin
        d_act = ACT_DIRECTORY;
        // No order_ref; locate+timestamp carry through the common fields.
      end
      default: begin
        d_act = ACT_UNKNOWN;
      end
    endcase
  end

  // ----------------------------------------------------------------------
  // Length check, evaluated at latch time.  len_ok_next is a function of
  // the message's type byte and total byte count, both known in the cycle
  // the last byte is committed.  The result is registered into len_ok_r
  // (see the byte collector) so the decode/counter logic sees a flop.
  // ----------------------------------------------------------------------
  wire [7:0] len_type_w = (msg_cnt == 8'd0) ? in_byte_r : msg_buf[0];
  wire [7:0] len_cnt_w  = msg_cnt + 8'd1;

  always @(*) begin
    case (len_type_w)
      ITCH_TYPE_ADD:        len_ok_next = (len_cnt_w == LEN_ADD);
      ITCH_TYPE_ADD_MPID:   len_ok_next = (len_cnt_w == LEN_ADD_MPID);
      ITCH_TYPE_EXEC:       len_ok_next = (len_cnt_w == LEN_EXEC);
      ITCH_TYPE_EXEC_PRICE: len_ok_next = (len_cnt_w == LEN_EXEC_PRICE);
      ITCH_TYPE_CANCEL:     len_ok_next = (len_cnt_w == LEN_CANCEL);
      ITCH_TYPE_DELETE:     len_ok_next = (len_cnt_w == LEN_DELETE);
      ITCH_TYPE_REPLACE:    len_ok_next = (len_cnt_w == LEN_REPLACE);
      ITCH_TYPE_DIR:        len_ok_next = (len_cnt_w == LEN_DIR);
      default:              len_ok_next = 1'b1;  // unknown type: accept
    endcase
  end

  // ----------------------------------------------------------------------
  // Output register: present decoded event on evt_valid
  // ----------------------------------------------------------------------
  reg [255:0] evt_r;
  reg         evt_valid_r;
  reg [15:0]  stock_locate_r;

  // Pack the struct into the flat 256-bit wire.  The concatenation below is
  // exactly 256 bits: 3 + 8 + 48 + 64 + 64 + 32 + 32 + 1 + 4 = 256.
  // Layout:
  //   [255:253] rsvd       3 bits
  //   [252:245] msg_type   8 bits
  //   [244:197] timestamp  48 bits
  //   [196:133] order_ref  64 bits
  //   [132: 69] aux_ref    64 bits
  //   [ 68: 37] price      32 bits
  //   [ 36:  5] shares     32 bits
  //   [  4:  4] side       1 bit
  //   [  3:  0] act        4 bits
  wire [255:0] evt_pack = {  3'd0,         // rsvd [255:253]
                            d_type,        // [252:245]
                            d_timestamp,   // [244:197]
                            d_order_ref,   // [196:133]
                            d_aux_ref,     // [132:69]
                            d_price,       // [68:37]
                            d_shares,      // [36:5]
                            d_side,        // [4]
                            d_act          // [3:0]
                         };

  assign evt         = evt_r;
  assign evt_valid   = evt_valid_r;
  assign stock_locate = stock_locate_r;
  assign ts_in_valid = enable && msg_latched && !evt_valid_r && len_ok_r;

  always @(posedge aclk) begin
    if (!aresetn) begin
      evt_r          <= 256'd0;
      evt_valid_r    <= 1'b0;
      stock_locate_r <= 16'd0;
    end else if (enable) begin
      if (msg_latched && !evt_valid_r && len_ok_r) begin
        // Latch the decoded event onto the output (only if length is valid);
        // hold until consumed.
        evt_r          <= evt_pack;
        evt_valid_r    <= 1'b1;
        stock_locate_r <= d_locate;
      end else if (evt_valid_r && evt_ready) begin
        // Output consumed; clear so the next message can be presented.
        evt_valid_r    <= 1'b0;
      end
    end
  end

  // ----------------------------------------------------------------------
  // Statistics counters
  // ----------------------------------------------------------------------
  reg [63:0] parse_cnt;      // messages parsed & emitted
  reg [31:0] drop_len_cnt;   // messages dropped due to length mismatch
  reg [31:0] err_type_cnt;   // messages with unknown type byte
  reg [31:0] stock_dir_cnt;  // stock directory messages

  wire evt_consume = evt_valid_r && evt_ready & enable & msg_latched & len_ok_r;
  wire len_fail    = msg_latched & !evt_valid_r & !len_ok_r & enable;
  wire type_unknown = (d_act == ACT_UNKNOWN) & msg_latched & !evt_valid_r & len_ok_r & enable;

  always @(posedge aclk) begin
    if (!aresetn) begin
      parse_cnt     <= 64'd0;
      drop_len_cnt  <= 32'd0;
      err_type_cnt  <= 32'd0;
      stock_dir_cnt <= 32'd0;
    end else if (enable) begin
      if (evt_consume)
        parse_cnt <= parse_cnt + 64'd1;

      if (len_fail)
        drop_len_cnt <= drop_len_cnt + 32'd1;

      if (type_unknown)
        err_type_cnt <= err_type_cnt + 32'd1;

      if (evt_consume && d_act == ACT_DIRECTORY)
        stock_dir_cnt <= stock_dir_cnt + 32'd1;
    end
  end

  // ----------------------------------------------------------------------
  // AXI4-Lite register slave (ctrl + RO stats)
  // ----------------------------------------------------------------------
  // ctrl_en and enable are declared near the top of the module (forward
  // declaration) because the byte collector and decode logic reference them
  // combinationally.  The write-channel logic below drives ctrl_en.
  reg        b_valid;
  reg        r_valid;
  reg [31:0] r_data;

  // ---- write channel --------------------------------------------------
  wire wr_fire = s_axi_awvalid && s_axi_wvalid && !b_valid;

  assign s_axi_awready = wr_fire;
  assign s_axi_wready  = wr_fire;

  always @(posedge aclk) begin
    if (!aresetn) begin
      b_valid <= 1'b0;
      ctrl_en <= 1'b0;
    end else begin
      if (wr_fire) begin
        b_valid <= 1'b1;
        if (s_axi_awaddr[4:2] == ADDR_CTRL && s_axi_wstrb[0])
          ctrl_en <= s_axi_wdata[0];
        // writes to RO registers are ignored by design
      end else if (s_axi_bvalid && s_axi_bready) begin
        b_valid <= 1'b0;
      end
    end
  end

  assign s_axi_bvalid = b_valid;
  assign s_axi_bresp  = 2'b00;   // OKAY

  // ---- read channel ---------------------------------------------------
  wire rd_fire = s_axi_arvalid && !r_valid;

  assign s_axi_arready = rd_fire;

  always @(posedge aclk) begin
    if (!aresetn) begin
      r_valid <= 1'b0;
      r_data  <= 32'd0;
    end else begin
      if (rd_fire) begin
        r_valid <= 1'b1;
        case (s_axi_araddr[4:2])
          ADDR_PARSE_CNT_LO:  r_data <= parse_cnt [31:0];
          ADDR_PARSE_CNT_HI:  r_data <= parse_cnt [63:32];
          ADDR_DROP_LEN_CNT:  r_data <= drop_len_cnt;
          ADDR_ERR_TYPE_CNT:  r_data <= err_type_cnt;
          ADDR_STOCK_DIR_CNT: r_data <= stock_dir_cnt;
          ADDR_CTRL:          r_data <= {31'b0, ctrl_en};
          default:            r_data <= 32'd0;
        endcase
      end else if (s_axi_rvalid && s_axi_rready) begin
        r_valid <= 1'b0;
      end
    end
  end

  assign s_axi_rvalid = r_valid;
  assign s_axi_rdata  = r_data;
  assign s_axi_rresp  = 2'b00;   // OKAY

endmodule
