// order_book: single-stock order book with price-level tracking and BBO.
//
// Consumes decoded ITCH events from itch_parse (evt + stock_locate) and
// maintains a price-level order book for one stock.  Tracks:
//   - order_map: order_ref → level_idx (direct-mapped, BRAM)
//   - level_table: level_idx → {price, shares, order_count} (BRAM)
//   - BBO: best bid and ask (price + level_idx), updated per event
//
// Supported actions (from evt[3:0] act field):
//   ACT_ADD (1)       : new order → allocate level (or reuse matching price),
//                       record in order_map, update level shares, update BBO
//   ACT_EXECUTE (2)   : reduce shares at the order's level, update BBO
//   ACT_CANCEL (3)    : reduce shares at the order's level, update BBO
//   ACT_DELETE (4)    : remove order from order_map
//   ACT_REPLACE (5)   : remove old order, add new order (may change price)
//   ACT_DIRECTORY (7) : no-op for book (stock_locate already captured)
//
// Processing is multi-cycle (FSM): ~6-8 cycles per event.  At 200 MHz this
// is ~35 ns/event, well within the ITCH message rate budget.
//
// AXI4-Lite register map (RW ctrl, RO stats):
//   0x00 BOOK_ORDER_CNT   RO  accepted adds minus deletes/cancels/executes
//                             NOT the order_map valid count: a direct-mapped collision
//                             replaces an entry without decrementing (round 9).
//   0x04 BOOK_LEVEL_CNT   RO  active levels (level_table valid count)
//   0x08 BOOK_BID_PRICE   RO  best bid price (0 = no bid)
//   0x0C BOOK_BID_SHARES  RO  best bid shares
//   0x10 BOOK_ASK_PRICE   RO  best ask price (0 = no ask)
//   0x14 BOOK_ASK_SHARES  RO  best ask shares
//   0x18 BOOK_ADD_CNT     RO  total ADD events processed
//   0x1C BOOK_EXE_CNT     RO  total EXECUTE events processed
//   0x20 BOOK_CAN_CNT     RO  total CANCEL events processed
//   0x24 BOOK_DEL_CNT     RO  total DELETE events processed
//   0x28 BOOK_REP_CNT     RO  total REPLACE events processed
//   0x2C BOOK_DROP_CNT    RO  events dropped (order not found / level full)
//   0x30 CTRL             RW  bit0=enable (default 0)
//                             bit1 is RESERVED and NOT implemented: only bit0
//                             is captured (ctrl_wdata_r <= s_axi_wdata[0]), so
//                             there is no soft reset.  The book state and all
//                             counters persist until a hardware reset.

`timescale 1ns / 1ps

module order_book #(
    parameter ORDERS      = 4096,  // order_map entries (2^ORD_ADDR_W)
    parameter LEVELS      = 256,   // level_table entries
    parameter ORD_ADDR_W  = 12,    // log2(ORDERS)
    parameter LEVEL_ADDR_W = 8     // log2(LEVELS)
)(
    input  wire        aclk,
    input  wire        aresetn,

    // AXI4-Lite slave (stats + control)
    input  wire [5:0]  s_axi_awaddr,
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
    input  wire [5:0]  s_axi_araddr,
    input  wire [2:0]  s_axi_arprot,
    input  wire        s_axi_arvalid,
    output wire        s_axi_arready,
    output wire [31:0] s_axi_rdata,
    output wire [1:0]  s_axi_rresp,
    output wire        s_axi_rvalid,
    input  wire        s_axi_rready,

    // Event input from itch_parse (valid/ready handshake)
    input  wire [255:0] evt,
    input  wire         evt_valid,
    output wire         evt_ready,
    input  wire [15:0]  stock_locate,

    // Status: high while FSM is processing an event (not in IDLE)
    output wire         busy,

    // Sideband: pulses for one cycle when event processing completes (ST_BBO).
    // Used by ts_hist (M5) to capture the completion timestamp t1.
    output wire         ts_done_valid
);

  // ----------------------------------------------------------------------
  // Action codes (must match itch_parse ACT_* encoding)
  // ----------------------------------------------------------------------
  localparam [3:0] ACT_UNKNOWN   = 4'd0;
  localparam [3:0] ACT_ADD       = 4'd1;
  localparam [3:0] ACT_EXECUTE   = 4'd2;
  localparam [3:0] ACT_CANCEL    = 4'd3;
  localparam [3:0] ACT_DELETE    = 4'd4;
  localparam [3:0] ACT_REPLACE   = 4'd5;
  localparam [3:0] ACT_DIRECTORY = 4'd7;

  // ----------------------------------------------------------------------
  // Extract fields from evt struct (matches itch_parse packing)
  // ----------------------------------------------------------------------
  wire [3:0]  act       = evt[3:0];
  wire        side      = evt[4];
  wire [31:0] price     = evt[68:37];
  wire [31:0] shares    = evt[36:5];
  wire [63:0] order_ref = evt[196:133];
  wire [63:0] aux_ref   = evt[132:69];

  // ----------------------------------------------------------------------
  // Control register (forward-declared: FSM references enable)
  // ----------------------------------------------------------------------
  reg enable;

  // ----------------------------------------------------------------------
  // AXI4-Lite register address decode
  // ----------------------------------------------------------------------
  localparam ADDR_ORDER_CNT   = 4'd0;  // 0x00
  localparam ADDR_LEVEL_CNT   = 4'd1;  // 0x04
  localparam ADDR_BID_PRICE   = 4'd2;  // 0x08
  localparam ADDR_BID_SHARES  = 4'd3;  // 0x0C
  localparam ADDR_ASK_PRICE   = 4'd4;  // 0x10
  localparam ADDR_ASK_SHARES  = 4'd5;  // 0x14
  localparam ADDR_ADD_CNT     = 4'd6;  // 0x18
  localparam ADDR_EXE_CNT     = 4'd7;  // 0x1C
  localparam ADDR_CAN_CNT     = 4'd8;  // 0x20
  localparam ADDR_DEL_CNT     = 4'd9;  // 0x24
  localparam ADDR_REP_CNT     = 4'd10; // 0x28
  localparam ADDR_DROP_CNT    = 4'd11; // 0x2C
  localparam ADDR_CTRL        = 4'd12; // 0x30

  // ----------------------------------------------------------------------
  // Order map: direct-mapped, order_ref[ORD_ADDR_W-1:0] → level_idx
  // ----------------------------------------------------------------------
  // Entry: {tag[63-ORD_ADDR_W:0], level_idx[LEVEL_ADDR_W-1:0], valid}
  // Tag = order_ref[63:ORD_ADDR_W] (upper bits not in address)
  localparam TAG_W = 64 - ORD_ADDR_W;
  localparam MAP_ENTRY_W = TAG_W + LEVEL_ADDR_W + 1;

  (* ram_style = "block" *) reg [MAP_ENTRY_W-1:0] order_map [0:ORDERS-1];

  // order_map port control.  Driven ONLY from the FSM always block; the RAM
  // always block below owns the array and the registered read data.  This
  // clean simple-dual-port template is what makes Vivado infer BRAM.  The
  // previous version mixed the array accesses with the FSM and the
  // ram_style attribute was rejected ("infeasible ... trying to implement
  // using LUTRAM"), leaving a 4K x 61 LUTRAM crossbar that dominated the
  // 200 MHz post-place critical path.
  reg                   map_we;
  reg [ORD_ADDR_W-1:0]  map_waddr;
  reg [MAP_ENTRY_W-1:0] map_wdata;
  reg [MAP_ENTRY_W-1:0] map_rdata_r;

  // ----------------------------------------------------------------------
  // Level table: level_idx → {price[31:0], shares[31:0], order_count[15:0], valid}
  // ----------------------------------------------------------------------
  localparam LEV_ENTRY_W = 32 + 32 + 16 + 1;

  (* ram_style = "block" *) reg [LEV_ENTRY_W-1:0] level_table [0:LEVELS-1];

  // ----------------------------------------------------------------------
  // BBO registers (best bid / ask per side)
  // ----------------------------------------------------------------------
  reg [31:0] bid_price;   // 0 = no bid
  reg [31:0] bid_shares;
  reg [LEVEL_ADDR_W-1:0] bid_level;  // level_idx of best bid
  reg        bid_valid;

  reg [31:0] ask_price;   // 0 = no ask
  reg [31:0] ask_shares;
  reg [LEVEL_ADDR_W-1:0] ask_level;  // level_idx of best ask
  reg        ask_valid;

  // BBO decision flags, computed in ST_LEV_UPDATE and consumed in ST_BBO.
  // Registering the 32-bit price comparisons keeps them out of the same
  // cycle as the shares adders/subtractors (a -1.2 ns post-synth path).
  reg bbo_bid_better, bbo_ask_better;   // new price beats current BBO
  reg bbo_bid_eq, bbo_ask_eq;           // price equals current BBO
  reg bbo_bid_affected, bbo_ask_affected; // level is the BBO level
  reg bbo_depleted;                       // level fully consumed

  // ----------------------------------------------------------------------
  // Stats counters
  // ----------------------------------------------------------------------
  reg [31:0] order_cnt;   // current orders in book
  reg [31:0] level_cnt;   // current active levels
  reg [31:0] add_cnt;
  reg [31:0] exe_cnt;
  reg [31:0] can_cnt;
  reg [31:0] del_cnt;
  reg [31:0] rep_cnt;
  reg [31:0] drop_cnt;

  // ----------------------------------------------------------------------
  // FSM state encoding
  // ----------------------------------------------------------------------
  localparam [3:0] ST_IDLE       = 4'd0;
  localparam [3:0] ST_MAP_READ   = 4'd1;  // read order_map
  localparam [3:0] ST_MAP_WAIT   = 4'd2;  // wait for map data
  localparam [3:0] ST_LEV_READ   = 4'd3;  // read level_table
  localparam [3:0] ST_LEV_WAIT   = 4'd4;  // wait for level data
  localparam [3:0] ST_LEV_UPDATE = 4'd5;  // compute + write level
  localparam [3:0] ST_MAP_WRITE  = 4'd6;  // write order_map
  localparam [3:0] ST_BBO        = 4'd7;  // update BBO
  localparam [3:0] ST_SEARCH     = 4'd8;  // search level_table for price match
  localparam [3:0] ST_SEARCH_WAIT= 4'd9;
  // 4'd10 is free: ST_DONE was declared here but never targeted and had no
  // case arm, so it was removed rather than left to occupy the last free
  // encoding. tools/check_fsm_liveness.py now fails on any dead state.
  localparam [3:0] ST_SEARCH_CHK = 4'd11;  // compare registered level data
  localparam [3:0] ST_MAP_CHK    = 4'd12;  // compare registered map data
  localparam [3:0] ST_LEV_CHK    = 4'd13;  // depletion compare from fabric copy
  localparam [3:0] ST_MAP_CMP    = 4'd14;  // register the tag compare

  // NOTE: 4 bits = 16 encodings. 14 are LIVE (0-9, 11-14); ST_DONE=10 is
  // declared but dead (never targeted, no case arm). That leaves 2 free
  // encodings: 10 and 15. Whoever adds a state will naturally pick 10 - the gap
  // in the sequence - and silently reuse the dead name; harmless but confusing,
  // so remove ST_DONE or reuse it deliberately.
  //
  // Widen to [4:0] before adding a THIRD state: a 4'd16 literal truncates to
  // 4'd0 = ST_IDLE, which re-enters idle silently instead of entering the new
  // state. mold64_reasm already went through this - its state widened 4->5 bits
  // when the byte-FIFO rewrite pushed past 16 states.
  // Enforced by tools/check_fsm_width.py (counts live states, not declarations).
  reg [3:0] state;

  // ----------------------------------------------------------------------
  // Event latch (captured when we accept an event)
  // ----------------------------------------------------------------------
  reg [3:0]  ev_act;
  reg        ev_side;
  reg [31:0] ev_price;
  reg [31:0] ev_shares;
  reg [63:0] ev_ref;
  reg [63:0] ev_aux;

  // ----------------------------------------------------------------------
  // Working registers for FSM
  // ----------------------------------------------------------------------
  reg [ORD_ADDR_W-1:0] map_addr;       // hash of order_ref
  reg [TAG_W-1:0]      map_tag;        // tag portion of order_ref
  reg [MAP_ENTRY_W-1:0] map_rdata;     // registered map read data
  reg [TAG_W-1:0]      map_rtag;
  reg [LEVEL_ADDR_W-1:0] map_ridx;
  reg                  map_rvalid;
  reg                  map_hit;        // tag match on last read
  // Tag match computed from the REGISTERED map fields, so the 52-bit
  // compare is register-to-register instead of sharing the BRAM DOBDO cycle.
  //
  // The compare is evaluated as two 26-bit halves whose results are
  // REGISTERED (map_hit_lo_r / map_hit_hi_r) before being combined.  A single
  // 52-bit equality infers one long carry chain whose output fans out into
  // the clock enables of every register written in ST_MAP_CHK's branches
  // (map_tag_reg[3]/CE among them); post-route that was the critical path at
  // -0.093 ns.  Registering each half keeps the CEs driven by flops whose
  // inputs are 26-bit compares, with map_hit_r formed one level deep.
  reg                  map_hit_lo_r, map_hit_hi_r, map_rvalid_r;
  wire                 map_hit_w = map_hit_lo_r && map_hit_hi_r && map_rvalid_r;

  reg [LEVEL_ADDR_W-1:0] lev_addr;     // level_table address
  reg [LEV_ENTRY_W-1:0]  lev_rdata;    // registered level read data
  reg [31:0]            lev_rprice;
  reg [31:0]            lev_rshares;
  reg [15:0]            lev_rcount;
  reg                   lev_rvalid;
  // Registered "level depletes on this execute/cancel" decision.  The
  // 32-bit lev_rshares > ev_shares compare used to drive the level_cnt
  // decrement enable directly (3 CARRY4 levels into a 32-flop CE).  Doing
  // it from lev_rdata_r instead put the BRAM output-register clock-to-out
  // in the same cycle as the compare (post-route WNS -0.543 ns).  The
  // fabric copy in ST_LEV_WAIT feeds ST_LEV_CHK, which registers the
  // result; ST_LEV_UPDATE and the BBO flags consume the flop.
  reg                   lev_depleted_r;

  reg [LEVEL_ADDR_W-1:0] next_free_level; // allocator pointer
  reg [LEVEL_ADDR_W-1:0] search_idx;      // linear search pointer
  reg [LEVEL_ADDR_W-1:0] found_level;     // level found during search
  reg                   search_found;
  reg                   lev_addr_set;     // lev_addr already set (skip re-read)

  // ----------------------------------------------------------------------
  // order_map RAM (simple dual port: 1 write, 1 synchronous read).
  // The read address is always map_addr and the data is registered here,
  // so the FSM sees it one cycle after ST_MAP_READ (same as before).
  // ----------------------------------------------------------------------
  always @(posedge aclk) begin
    if (map_we)
      order_map[map_waddr] <= map_wdata;
    map_rdata_r <= order_map[map_addr];
  end

  // level_table read data (registered output, written only in the FSM block)
  reg [LEV_ENTRY_W-1:0] lev_rdata_r;

  // ----------------------------------------------------------------------
  // Event accepted when FSM is in IDLE and evt_valid is high
  // ----------------------------------------------------------------------
  wire evt_accept = (state == ST_IDLE) && evt_valid && enable;
  assign evt_ready = evt_accept;
  assign ts_done_valid = enable && (state == ST_BBO);
  assign busy      = (state != ST_IDLE);

  // ----------------------------------------------------------------------
  // Main FSM
  // ----------------------------------------------------------------------
  always @(posedge aclk) begin
    if (!aresetn) begin
      state <= ST_IDLE;
      // NOTE: `enable` is intentionally NOT assigned here.  It is driven
      // only by the AXI4-Lite write block below.  Driving it from two
      // always blocks made synthesis keep the constant driver and ignore
      // the AXI one, which tied enable=0 and pruned the entire book
      // (design -> 4 LUTs / 2 FFs).  Caught by hierarchical utilization.
      // Reset BBO
      bid_price <= 32'd0; bid_shares <= 32'd0; bid_level <= {LEVEL_ADDR_W{1'b0}}; bid_valid <= 1'b0;
      ask_price <= 32'd0; ask_shares <= 32'd0; ask_level <= {LEVEL_ADDR_W{1'b0}}; ask_valid <= 1'b0;
      bbo_bid_better <= 1'b0; bbo_ask_better <= 1'b0;
      bbo_bid_eq <= 1'b0; bbo_ask_eq <= 1'b0;
      bbo_bid_affected <= 1'b0; bbo_ask_affected <= 1'b0;
      bbo_depleted <= 1'b0;
      lev_depleted_r <= 1'b0;
      // Reset stats
      order_cnt <= 32'd0; level_cnt <= 32'd0;
      add_cnt <= 32'd0; exe_cnt <= 32'd0; can_cnt <= 32'd0;
      del_cnt <= 32'd0; rep_cnt <= 32'd0; drop_cnt <= 32'd0;
      // Reset allocator
      next_free_level <= {LEVEL_ADDR_W{1'b0}};
      // Reset working regs
      map_addr <= {ORD_ADDR_W{1'b0}};
      lev_addr <= {LEVEL_ADDR_W{1'b0}};
      map_we    <= 1'b0;
      map_waddr <= {ORD_ADDR_W{1'b0}};
      map_wdata <= {MAP_ENTRY_W{1'b0}};
      map_hit <= 1'b0;
      search_found <= 1'b0;
      found_level <= {LEVEL_ADDR_W{1'b0}};
      search_idx <= {LEVEL_ADDR_W{1'b0}};
    end else begin
      // map_we defaults low every cycle (also while disabled, so a strobe
      // left high by the last event cannot keep rewriting the map).
      map_we <= 1'b0;
      if (enable) begin
      case (state)

        // ----- IDLE: accept next event -----------------------------------
        ST_IDLE: begin
          if (evt_valid) begin
            // Latch event fields
            ev_act   <= act;
            ev_side  <= side;
            ev_price <= price;
            ev_shares<= shares;
            ev_ref   <= order_ref;
            ev_aux   <= aux_ref;

            // Compute map address and tag
            map_addr <= order_ref[ORD_ADDR_W-1:0];
            map_tag  <= order_ref[63:ORD_ADDR_W];

            case (act)
              ACT_ADD: begin
                add_cnt <= add_cnt + 32'd1;
                // For ADD: read order_map to check for duplicate
                state <= ST_MAP_READ;
              end
              ACT_EXECUTE, ACT_CANCEL: begin
                if (act == ACT_EXECUTE)
                  exe_cnt <= exe_cnt + 32'd1;
                else
                  can_cnt <= can_cnt + 32'd1;
                // Read order_map to find level
                state <= ST_MAP_READ;
              end
              ACT_DELETE: begin
                del_cnt <= del_cnt + 32'd1;
                // Read order_map to find and invalidate
                state <= ST_MAP_READ;
              end
              ACT_REPLACE: begin
                rep_cnt <= rep_cnt + 32'd1;
                // Read order_map for old_ref
                state <= ST_MAP_READ;
              end
              ACT_DIRECTORY, ACT_UNKNOWN: begin
                // No book action; stay in IDLE (event consumed)
                state <= ST_IDLE;
              end
              default: state <= ST_IDLE;
            endcase
          end
        end

        // ----- ST_MAP_READ: initiate order_map read ---------------------
        // map_addr was set in ST_IDLE (or earlier).  Read the BRAM now —
        // the address is stable, so the data is correct this cycle.
        ST_MAP_READ: begin
          // The order_map read happens every cycle in its RAM always block;
          // map_rdata_r is valid in ST_MAP_WAIT.
          state <= ST_MAP_WAIT;
        end

        // ----- ST_MAP_WAIT: register the map read data -------------------
        // The BRAM output register (DOBDO) has a ~2.5 ns clock-to-out; the
        // 52-bit tag compare happens in ST_MAP_CHK from these flops instead
        // of sharing the BRAM output cycle.
        ST_MAP_WAIT: begin
          map_rdata  <= map_rdata_r;
          map_rtag   <= map_rdata_r[MAP_ENTRY_W-1:LEVEL_ADDR_W+1];
          map_ridx   <= map_rdata_r[LEVEL_ADDR_W:1];
          map_rvalid <= map_rdata_r[0];
          state <= ST_MAP_CMP;
        end

        // ----- ST_MAP_CMP: register the tag compare ----------------------
        // map_rtag / map_rvalid were captured in ST_MAP_WAIT, so both
        // operands here are plain flops (no BRAM clock-to-out in the path).
        // The two 26-bit halves are registered and combined one level deep in
        // map_hit_w, which keeps the ST_MAP_CHK clock enables off a 52-bit
        // carry chain.  Costs exactly one extra cycle per event.
        ST_MAP_CMP: begin
          map_hit_lo_r <= (map_rtag[(TAG_W/2)-1:0] == map_tag[(TAG_W/2)-1:0]);
          map_hit_hi_r <= (map_rtag[TAG_W-1:TAG_W/2] == map_tag[TAG_W-1:TAG_W/2]);
          map_rvalid_r <= map_rvalid;
          state <= ST_MAP_CHK;
        end

        // ----- ST_MAP_CHK: decode from registered map fields -------------
        ST_MAP_CHK: begin
          map_hit <= map_hit_w;
          case (ev_act)
            ACT_ADD: begin
              if (map_hit_w) begin
                // Duplicate add: drop (shouldn't happen in valid feed)
                drop_cnt <= drop_cnt + 32'd1;
                state <= ST_IDLE;
              end else begin
                // Search for existing level with matching price
                search_idx <= {LEVEL_ADDR_W{1'b0}};
                search_found <= 1'b0;
                found_level <= {LEVEL_ADDR_W{1'b0}};
                state <= ST_SEARCH;
              end
            end
            ACT_EXECUTE, ACT_CANCEL: begin
              if (!map_hit_w) begin
                // Order not found: drop
                drop_cnt <= drop_cnt + 32'd1;
                state <= ST_IDLE;
              end else begin
                // Read the level — set lev_addr and skip re-read in ST_LEV_READ
                lev_addr <= map_ridx;
                found_level <= map_ridx;
                lev_addr_set <= 1'b1;
                state <= ST_LEV_READ;
              end
            end
            ACT_DELETE: begin
              if (!map_hit_w) begin
                drop_cnt <= drop_cnt + 32'd1;
                state <= ST_IDLE;
              end else begin
                // Invalidate order_map entry
                map_we    <= 1'b1;
                map_waddr <= map_addr;
                map_wdata <= {map_tag, map_ridx, 1'b0};
                if (order_cnt > 0) order_cnt <= order_cnt - 32'd1;
                state <= ST_IDLE;
              end
            end
            ACT_REPLACE: begin
              if (!map_hit_w) begin
                drop_cnt <= drop_cnt + 32'd1;
                state <= ST_IDLE;
              end else begin
                // Invalidate old order_map entry
                map_we    <= 1'b1;
                map_waddr <= map_addr;
                map_wdata <= {map_tag, map_ridx, 1'b0};
                // Now treat as ADD for new_ref
                map_addr <= aux_ref[ORD_ADDR_W-1:0];
                map_tag  <= aux_ref[63:ORD_ADDR_W];
                ev_ref   <= aux_ref;
                // Search for level with new price
                search_idx <= {LEVEL_ADDR_W{1'b0}};
                search_found <= 1'b0;
                found_level <= {LEVEL_ADDR_W{1'b0}};
                state <= ST_SEARCH;
              end
            end
            default: state <= ST_IDLE;
          endcase
        end

        // ----- ST_SEARCH: linear scan level_table for price match --------
        // Read level at search_idx.  We read level_table[search_idx] directly
        // (search_idx is a stable register) and capture into lev_rdata_r.
        ST_SEARCH: begin
          lev_addr <= search_idx;
          lev_rdata_r <= level_table[search_idx];
          state <= ST_SEARCH_WAIT;
        end

        // Register the level data one extra cycle.  The BRAM output register
        // (DOBDO) has a ~2.5 ns clock-to-out; feeding it straight into the
        // 32-bit price compare made that a -1.5 ns post-synth path.  With
        // lev_rdata as a fabric flop the compare is register-to-register.
        // Costs one cycle per searched level (search is already 2 cycles).
        ST_SEARCH_WAIT: begin
          lev_rdata <= lev_rdata_r;
          state <= ST_SEARCH_CHK;
        end

        ST_SEARCH_CHK: begin
          // Check if this level matches our price
          if (lev_rdata[0] && lev_rdata[LEV_ENTRY_W-1:49] == ev_price) begin
            search_found <= 1'b1;
            found_level <= search_idx;
            state <= ST_LEV_READ;  // re-read to confirm (or use cached)
          end else if (search_idx == LEVELS - 1) begin
            // Exhausted search: allocate new level
            search_found <= 1'b0;
            found_level <= next_free_level;
            // Round 7: next_free_level is LEVEL_ADDR_W bits, so it can never represent LEVELS
            // itself - comparing it to LEVELS is always false and the table overwrites level 0.
            // level_cnt is 32 bits and counts every allocation, so it can.
            if (level_cnt >= LEVELS) begin
              // Level table full: drop
              drop_cnt <= drop_cnt + 32'd1;
              state <= ST_IDLE;
            end else begin
              state <= ST_LEV_UPDATE;
            end
          end else begin
            search_idx <= search_idx + 1'b1;
            state <= ST_SEARCH;
          end
        end

        // ----- ST_LEV_READ: read level_table -----------------------------
        // Read level_table[found_level] directly.  If lev_addr_set is true
        // (EXECUTE/CANCEL path), lev_addr already holds the target.
        ST_LEV_READ: begin
          if (!lev_addr_set)
            lev_addr <= found_level;
          lev_addr_set <= 1'b0;
          lev_rdata_r <= level_table[lev_addr_set ? lev_addr : found_level];
          state <= ST_LEV_WAIT;
        end

        ST_LEV_WAIT: begin
          lev_rdata  <= lev_rdata_r;
          lev_rprice <= lev_rdata_r[LEV_ENTRY_W-1:49];
          lev_rshares<= lev_rdata_r[48:17];
          lev_rcount <= lev_rdata_r[16:1];
          lev_rvalid <= lev_rdata_r[0];
          // lev_rdata_r is the BRAM output register (DOA_REG=1), so its
          // clock-to-out (~2.4 ns) cannot share a cycle with the 32-bit
          // depletion compare.  ST_LEV_CHK does the compare from the fabric
          // copy (lev_rshares) and registers the result for ST_LEV_UPDATE.
          state <= ST_LEV_CHK;
        end

        // ----- ST_LEV_CHK: depletion decision from fabric registers ------
        ST_LEV_CHK: begin
          lev_depleted_r <= (lev_rshares <= ev_shares);
          state <= ST_LEV_UPDATE;
        end

        // ----- ST_LEV_UPDATE: compute new level data, write back ---------
        ST_LEV_UPDATE: begin
          // BBO decisions are computed here (one cycle ahead of ST_BBO) so
          // the 32-bit price compares are register-to-register.  All inputs
          // (ev_*, bid/ask, found_level, lev_rshares) are stable until the
          // BBO update, including across the intervening ST_MAP_WRITE.
          bbo_bid_better   <= !bid_valid || (ev_price > bid_price);
          bbo_ask_better   <= !ask_valid || (ev_price < ask_price);
          bbo_bid_eq       <= (ev_price == bid_price);
          bbo_ask_eq       <= (ev_price == ask_price);
          bbo_bid_affected <= (ev_side == 1'b0) && bid_valid &&
                              (found_level == bid_level);
          bbo_ask_affected <= (ev_side == 1'b1) && ask_valid &&
                              (found_level == ask_level);
          bbo_depleted     <= lev_depleted_r;
          case (ev_act)
            ACT_ADD: begin
              if (search_found) begin
                // Reuse existing level: increment shares + order_count
                level_table[found_level] <= {ev_price, lev_rshares + ev_shares, lev_rcount + 16'd1, 1'b1};
              end else begin
                // Allocate new level
                level_table[next_free_level] <= {ev_price, ev_shares, 16'd1, 1'b1};
                found_level <= next_free_level;
                if (next_free_level < LEVELS - 1)
                  next_free_level <= next_free_level + 1'b1;
                level_cnt <= level_cnt + 32'd1;
              end
              // Write order_map
              state <= ST_MAP_WRITE;
            end
            ACT_EXECUTE, ACT_CANCEL: begin
              // Reduce shares.  lev_depleted_r was registered in
              // ST_LEV_WAIT (lev_rshares <= ev_shares).
              if (!lev_depleted_r) begin
                level_table[found_level] <= {lev_rprice, lev_rshares - ev_shares, lev_rcount, 1'b1};
              end else begin
                // Level depleted: mark invalid
                level_table[found_level] <= {lev_rprice, 32'd0, 16'd0, 1'b0};
                if (level_cnt > 0) level_cnt <= level_cnt - 32'd1;
              end
              // Invalidate order_map (order fully executed/cancelled)
              map_we    <= 1'b1;
              map_waddr <= map_addr;
              map_wdata <= {map_tag, map_ridx, 1'b0};
              if (order_cnt > 0) order_cnt <= order_cnt - 32'd1;
              state <= ST_BBO;
            end
            default: state <= ST_IDLE;
          endcase
        end

        // ----- ST_MAP_WRITE: write order_map entry -----------------------
        ST_MAP_WRITE: begin
          map_we    <= 1'b1;
          map_waddr <= map_addr;
          map_wdata <= {map_tag, found_level, 1'b1};
          order_cnt <= order_cnt + 32'd1;
          state <= ST_BBO;
        end

        // ----- ST_BBO: update best bid/ask --------------------------------
        ST_BBO: begin
          // Re-read the affected level to get current data
          lev_addr <= found_level;
          // For now, do a simple BBO update: scan is expensive, so we
          // just compare the affected level against current BBO.
          // A full re-scan would be done periodically or on demand.
          // For the first cut, update BBO if the affected level is better.
          case (ev_act)
            ACT_ADD: begin
              if (!ev_side) begin
                // Buy side: update bid if price is higher
                if (bbo_bid_better) begin
                  bid_price <= ev_price;
                  bid_shares<= ev_shares;
                  bid_level <= found_level;
                  bid_valid <= 1'b1;
                end else if (bbo_bid_eq) begin
                  bid_shares <= bid_shares + ev_shares;
                end
              end else begin
                // Sell side: update ask if price is lower
                if (bbo_ask_better) begin
                  ask_price <= ev_price;
                  ask_shares<= ev_shares;
                  ask_level <= found_level;
                  ask_valid <= 1'b1;
                end else if (bbo_ask_eq) begin
                  ask_shares <= ask_shares + ev_shares;
                end
              end
            end
            ACT_EXECUTE, ACT_CANCEL: begin
              // If the affected level was the BBO:
              //   - if fully depleted: invalidate BBO
              //   - if partially executed: reduce BBO shares
              if (bbo_bid_affected) begin
                if (bbo_depleted) begin
                  bid_valid <= 1'b0; bid_price <= 32'd0; bid_shares <= 32'd0;
                end else begin
                  bid_shares <= bid_shares - ev_shares;
                end
              end
              if (bbo_ask_affected) begin
                if (bbo_depleted) begin
                  ask_valid <= 1'b0; ask_price <= 32'd0; ask_shares <= 32'd0;
                end else begin
                  ask_shares <= ask_shares - ev_shares;
                end
              end
            end
            default: ;
          endcase
          state <= ST_IDLE;
        end

        default: state <= ST_IDLE;
      endcase
      end // if (enable)
    end
  end

  // ----------------------------------------------------------------------
  // AXI4-Lite stats + control
  // ----------------------------------------------------------------------
  reg        b_valid;
  reg        r_valid;
  reg [31:0] r_data;

  wire wr_fire = s_axi_awvalid && s_axi_wvalid && !b_valid;

  // Registered CTRL write strobe.
  //
  // enable is loaded from a REGISTERED copy of the write data instead of
  // straight off wr_fire.  The combinational chain
  //   PS MAXIGP0WVALID -> interconnect arbiter -> s_axi_wvalid
  //                    -> s_axi_wready (3 loads, 2.0 ns route) -> enable_reg
  // was the last failing path (-0.003 ns, reproducible across placements).
  // Capturing the write into one register and loading `enable` from it on the
  // next cycle removes the combinational wready fan-out from the enable path.
  // AXI-Lite semantics are unchanged: AW/W are still consumed on the same
  // edge and BVALID still asserts on the cycle after the handshake.
  reg        ctrl_wr_r;
  reg        ctrl_wdata_r;

  assign s_axi_awready = wr_fire;
  assign s_axi_wready  = wr_fire;

  always @(posedge aclk) begin
    if (!aresetn) begin
      b_valid      <= 1'b0;
      enable       <= 1'b0;
      ctrl_wr_r    <= 1'b0;
      ctrl_wdata_r <= 1'b0;
    end else begin
      // Capture the control write, then apply it on the following cycle.
      ctrl_wr_r    <= wr_fire && (s_axi_awaddr[5:2] == ADDR_CTRL) &&
                      s_axi_wstrb[0];
      ctrl_wdata_r <= s_axi_wdata[0];
      if (ctrl_wr_r)
        enable <= ctrl_wdata_r;

      if (wr_fire) begin
        b_valid <= 1'b1;
      end else if (s_axi_bvalid && s_axi_bready) begin
        b_valid <= 1'b0;
      end
    end
  end

  assign s_axi_bvalid = b_valid;
  assign s_axi_bresp  = 2'b00;

  // Register the read address before the read mux.  Feeding s_axi_araddr
  // directly into the case put the PS7 -> interconnect -> order_book route
  // on the read-data path (post-route WNS -0.729 ns, 2 logic levels and
  // 4.75 ns of route).  A one-cycle read latency is allowed by AXI4-Lite.
  reg        rd_pending;
  reg [5:0]  araddr_r;
  wire rd_fire = s_axi_arvalid && !r_valid && !rd_pending;
  assign s_axi_arready = rd_fire;

  always @(posedge aclk) begin
    if (!aresetn) begin
      r_valid    <= 1'b0;
      r_data     <= 32'd0;
      rd_pending <= 1'b0;
      araddr_r   <= 6'd0;
    end else if (rd_fire) begin
      rd_pending <= 1'b1;
      araddr_r   <= s_axi_araddr;
    end else if (rd_pending) begin
      rd_pending <= 1'b0;
      r_valid    <= 1'b1;
        case (araddr_r[5:2])
          ADDR_ORDER_CNT:  r_data <= order_cnt;
          ADDR_LEVEL_CNT:  r_data <= level_cnt;
          ADDR_BID_PRICE:  r_data <= bid_price;
          ADDR_BID_SHARES: r_data <= bid_shares;
          ADDR_ASK_PRICE:  r_data <= ask_price;
          ADDR_ASK_SHARES: r_data <= ask_shares;
          ADDR_ADD_CNT:    r_data <= add_cnt;
          ADDR_EXE_CNT:    r_data <= exe_cnt;
          ADDR_CAN_CNT:    r_data <= can_cnt;
          ADDR_DEL_CNT:    r_data <= del_cnt;
          ADDR_REP_CNT:    r_data <= rep_cnt;
          ADDR_DROP_CNT:   r_data <= drop_cnt;
          ADDR_CTRL:       r_data <= {31'b0, enable};
          default:         r_data <= 32'd0;
        endcase
    end else if (s_axi_rvalid && s_axi_rready) begin
      r_valid <= 1'b0;
    end
  end

  assign s_axi_rvalid = r_valid;
  assign s_axi_rdata  = r_data;
  assign s_axi_rresp  = 2'b00;

endmodule
