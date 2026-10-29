// ts_hist: measurement framework for the nasdaq FPGA overlay (M5).
//
// Collects four classes of statistics, all readable via AXI4-Lite:
//   US1 — 64-bit free-running timestamp counter @ 200 MHz (5 ns resolution)
//   US2 — sideband timestamp: t0 captured at pipeline ingress (itch_parse
//         presents an event), t1 at pipeline completion (order_book finishes);
//         DELTA = t1 - t0 is the PL-internal latency per message.
//   US3 — latency histogram: 256 buckets × 8 clock cycles (40 ns @ 200 MHz),
//         covering 0–2048 cycles (0–10.24 us).  Plus min/max/sum/count so the
//         PS can compute P50/P95/P99 without reading raw samples.
//   US4 — per-type counters: 16 counters indexed by ITCH act field, plus a
//         drop counter and an overflow counter.
//
// The timestamp counter and statistics run in the 200 MHz design clock domain.
// All sideband inputs (ingress_valid, completion_valid, msg_type, msg_valid)
// are synchronous single-cycle pulses.
//
// AXI4-Lite register map (word address = byte_addr[11:2]):
//   Word  Name        Access  Description
//   0     CTRL        RW      bit0=enable; bit1=stats_reset (self-clearing)
//   1     T0_LO       RO      last ingress timestamp [31:0]
//   2     T0_HI       RO      last ingress timestamp [63:32]
//   3     T1_LO       RO      last completion timestamp [31:0]
//   4     T1_HI       RO      last completion timestamp [63:32]
//   5     DELTA       RO      last delta (T1 - T0), 32-bit
//   6     MIN         RO      minimum delta seen
//   7     MAX         RO      maximum delta seen
//   8     SUM_LO      RO      accumulated delta sum [31:0]
//   9     SUM_HI      RO      accumulated delta sum [63:32]
//   10    COUNT_LO    RO      number of completed measurements [31:0]
//   11    COUNT_HI    RO      number of completed measurements [63:32]
//   12..255 HIST      RO      256 histogram buckets (4 B each, 1 KB)
//   256..271 TYPE_CNT RO      16 per-type counters (act field 0..15)
//   272   DROP_CNT    RO      messages dropped (per-type index 16 — reserved)
//   273   OVERFLOW    RO      histogram overflows (delta > max bucket range)
//   286   TSNOW       RO      free-running timestamp counter, low 32 bits
//                             (additive; lets SW bound a window in PL cycles)
//
// Note: histogram buckets cover delta[10:3] (8-cycle granularity). Deltas
// larger than 2047 cycles are clamped to bucket 255 and OVERFLOW is incremented.

`timescale 1ns / 1ps

module ts_hist #(
    parameter HIST_BINS   = 256,   // number of histogram buckets
    parameter HIST_BIN_W  = 8,     // log2(HIST_BINS)
    parameter TYPE_BINS   = 16     // per-type counter slots
)(
    input  wire        aclk,
    input  wire        aresetn,

    // AXI4-Lite slave (12-bit byte address: 256 hist + 12 fixed + 16 type + 2 = 286 words, 1144 B)
    input  wire [11:0] s_axi_awaddr,
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
    input  wire [11:0] s_axi_araddr,
    input  wire [2:0]  s_axi_arprot,
    input  wire        s_axi_arvalid,
    output wire        s_axi_arready,
    output wire [31:0] s_axi_rdata,
    output wire [1:0]  s_axi_rresp,
    output wire        s_axi_rvalid,
    input  wire        s_axi_rready,

    // Sideband timestamp triggers (synchronous single-cycle pulses)
    input  wire        ingress_valid,     // pulse: book accepted an event (t0 capture)
    input  wire        completion_valid,  // pulse: book finished processing (t1 capture)

    // Per-type message input (valid when ingress_valid pulses)
    input  wire [3:0]  msg_type           // act field from itch_parse
);

  // ----------------------------------------------------------------------
  // Word-address constants (araddr/awaddr are byte addresses; we use [11:2])
  // ----------------------------------------------------------------------
  localparam [9:0] ADDR_CTRL       = 10'd0;   // byte 0x00
  localparam [9:0] ADDR_T0_LO      = 10'd1;   // byte 0x04
  localparam [9:0] ADDR_T0_HI      = 10'd2;   // byte 0x08
  localparam [9:0] ADDR_T1_LO      = 10'd3;   // byte 0x0C
  localparam [9:0] ADDR_T1_HI      = 10'd4;   // byte 0x10
  localparam [9:0] ADDR_DELTA      = 10'd5;   // byte 0x14
  localparam [9:0] ADDR_MIN        = 10'd6;   // byte 0x18
  localparam [9:0] ADDR_MAX        = 10'd7;   // byte 0x1C
  localparam [9:0] ADDR_SUM_LO     = 10'd8;   // byte 0x20
  localparam [9:0] ADDR_SUM_HI     = 10'd9;   // byte 0x24
  localparam [9:0] ADDR_COUNT_LO   = 10'd10;  // byte 0x28
  localparam [9:0] ADDR_COUNT_HI   = 10'd11;  // byte 0x2C
  localparam [9:0] ADDR_HIST_BASE  = 10'd12;  // byte 0x30
  localparam [9:0] ADDR_TYPE_BASE  = 10'd12 + HIST_BINS;       // 268, byte 0x430
  localparam [9:0] ADDR_DROP_CNT   = 10'd12 + HIST_BINS + 16;  // 284, byte 0x470
  localparam [9:0] ADDR_OVERFLOW   = 10'd12 + HIST_BINS + 17;  // 285, byte 0x474
  // 286-287: low 32 bits of the free-running timestamp counter.  Additive
  // extension (word 286 was unused): lets software bound a measurement
  // window by the *PL* clock instead of by host wall-clock time, which is
  // what the DMA/host round trip measures.  Two reads bracket the replay
  // and the difference is PL cycles at 200 MHz (5 ns each).
  localparam [9:0] ADDR_TSNOW      = 10'd12 + HIST_BINS + 18;  // 286, byte 0x478

  // ----------------------------------------------------------------------
  // Control register (forward-declared: counter and stats reference enable)
  // ----------------------------------------------------------------------
  reg enable_reg;

  // AXI4-Lite register state (forward-declared: wr_fire/rd_fire reference
  // b_valid/r_valid, and the write channel drives enable_reg).
  reg        b_valid;
  reg        r_valid;
  reg [31:0] r_data;

  // Write fires when both AW and W are valid and no outstanding write response
  // is pending (b_valid high). Read fires when AR is valid and no outstanding
  // read data is pending (r_valid high).
  wire wr_fire = s_axi_awvalid && s_axi_wvalid && !b_valid;
  // rd_fire is declared in the read channel below (it also depends on
  // rd_pending, the registered-read-address handshake).

  // ----------------------------------------------------------------------
  // US1: 64-bit free-running timestamp counter
  // ----------------------------------------------------------------------
  reg [63:0] timestamp_counter;

  always @(posedge aclk) begin
    if (!aresetn) begin
      timestamp_counter <= 64'd0;
    end else if (enable_reg) begin
      timestamp_counter <= timestamp_counter + 64'd1;
    end
  end

  // ----------------------------------------------------------------------
  // US2: Sideband timestamp capture
  // ----------------------------------------------------------------------
  reg [63:0] t0_reg;
  reg [63:0] t1_reg;
  reg [31:0] delta_reg;
  reg [31:0] min_delta;
  reg [31:0] max_delta;
  // Registered compare results, so the 32-bit magnitude compares do not sit between a register output
  // and that same register's clock enable.
  //
  // Failing path before this change:
  //     ts_hist_0/inst/max_delta_reg[8]/C -> ts_hist_0/inst/max_delta_reg[1]/CE   slack 0.008 ns
  // which is one bit of max_delta feeding a 32-bit CARRY4 chain feeding max_delta's own enable.
  reg [63:0] sum_delta;
  reg [63:0] count_delta;

  // Raw delta: 64-bit subtract, registered as stage 1.  Keeping the
  // subtractor output out of the bucket/min/max logic splits the old
  // timestamp_counter -> 64-bit subtract -> compare path across two cycles.
  wire [63:0] delta_w;
  assign delta_w = timestamp_counter - t0_reg;
  reg  [63:0] delta64_r;

  // Histogram bucket index from the REGISTERED delta (stage 2).
  // delta[10:3], clamped if delta > 2047.
  wire delta_overflow = |delta64_r[63:11];
  wire [HIST_BIN_W-1:0] bucket_idx =
      delta_overflow ? {HIST_BIN_W{1'b1}} : delta64_r[HIST_BIN_W+2:3];

  // ----------------------------------------------------------------------
  // US3: Histogram (256 x 32-bit, distributed RAM)
  //
  // Do NOT reset the array with a for-loop in the clocked block: an array
  // reset makes Vivado build the histogram out of 8192 flops plus a 256:1
  // mux tree.  That mux was the 200 MHz critical path (10.1 ns data path,
  // WNS -5.26 ns post-place).  Stats reset instead walks a 256-cycle clear
  // scan through the normal synchronous write port.
  //
  // The array is read at the registered bucket (stage 2, synchronous) and
  // incrementally written back one cycle later (stage 3).  The AXI read
  // mux keeps its asynchronous read; LUTRAM supports it, BRAM would not.
  // ----------------------------------------------------------------------
  (* ram_style = "distributed" *) reg [31:0] hist [0:HIST_BINS-1];

  // ----------------------------------------------------------------------
  // US4: Per-type counters + drop + overflow
  // ----------------------------------------------------------------------
  reg [31:0] type_cnt [0:TYPE_BINS-1];
  reg [31:0] drop_cnt;
  reg [31:0] overflow_cnt;

  // Registered CTRL-write pulse and its data bits.  Driving the stats
  // pipeline straight from the AXI-Lite write strobe put the PS7 ->
  // interconnect -> ts_hist propagation delay inside a clock-enable cone
  // that fans out to ~1900 endpoints (post-route WNS -1.239 ns: every hist
  // LUTRAM write address/WE and every pipeline flop enable).  Registering
  // the write once decouples the AXI timing from the stats logic; software
  // sees a one-cycle-later effect, which is invisible over AXI.
  reg  ctrl_wr_r;
  reg  ctrl_en_r;
  reg  ctrl_srst_r;
  wire stats_reset_wr = ctrl_wr_r && ctrl_srst_r;

  // stats_reset_pending: reflects whether a reset was requested but not yet
  // applied — used for testbench observability. In practice the reset takes
  // effect on the cycle after the write, so this is always 0.
  wire stats_reset_pending = 1'b0;

  // ----------------------------------------------------------------------
  // Stats update (US2 + US3 + US4 combined)
  //
  // The histogram update is the critical timing path at 200 MHz.  It is
  // pipelined into four stages so every hop is register-to-register short:
  //
  //   Stage 1 (completion_valid fires):
  //     Register the raw 64-bit delta.  The subtractor ends at delta64_r.
  //   Stage 2 (next cycle):
  //     Compute bucket_idx/overflow/min/max/sum from delta64_r.
  //   Stage 3 (next cycle):
  //     Read hist[bucket_r].  bucket_r is a register, so the LUTRAM read has
  //     a registered address (register → RAM → register).
  //   Stage 4 (next cycle):
  //     Increment the registered read data and write it back to bucket_r2.
  //
  // This adds three cycles of latency to the histogram write-back, which is
  // acceptable for a statistics module.  Completion pulses are at least
  // seven cycles apart (order_book FSM), so back-to-back updates cannot
  // collide.
  //
  // Stats reset is a 256-cycle clear scan over the write port (see above).
  //
  // The per-type counter (type_cnt) has the same read-modify-write structure
  // but uses a register array (not RAM), so its path is shorter; we still
  // pipeline it for symmetry and to avoid a separate long path.
  // ----------------------------------------------------------------------
  integer i;

  // Pipeline stage 1 registers: capture completion event context
  reg [HIST_BIN_W-1:0] bucket_r; // registered bucket_idx
  reg        overflow_r;         // registered delta_overflow
  reg [3:0]  msg_type_r;         // registered msg_type (for type_cnt)
  reg        completion_r;       // completion_valid delayed 1 cycle
  reg        ingress_r;          // ingress_valid delayed 1 cycle

  // Pipeline stage 2/3 registers
  reg [31:0] hist_rdata;         // hist[bucket_r], registered read data
  reg [31:0] type_rdata;         // type_cnt read data
  reg        completion_r2;      // bucket_r is being read this cycle
  reg        completion_r3;      // hist_rdata is valid this cycle
  reg        completion_r4;      // hist_wdata_r is valid this cycle (write)
  reg [HIST_BIN_W-1:0] bucket_r2;// bucket_r delayed (stage 3 read address)
  reg [HIST_BIN_W-1:0] bucket_r3;// bucket_r2 delayed (stage 5 write address)
  reg [31:0] hist_wdata_r;       // incremented histogram value
  reg        overflow_r2;        // overflow_r delayed

  // Registered RAM write port.  The histogram clear scan and the normal
  // increment used to share a combinational address mux straight into the
  // LUTRAM address pins: 4 LUT levels plus 3.3 ns of route to 128 RAM
  // primitives (post-route WNS -0.541 ns).  Registering WE/address/data
  // makes the RAM inputs one register hop from a flop; one cycle of extra
  // write latency is irrelevant for statistics.
  reg                   hist_we_r;
  reg [HIST_BIN_W-1:0]  hist_waddr_r;
  reg [31:0]            hist_wd_r;

  // Stats reset clear scan (one histogram entry per cycle)
  reg        clear_busy;
  reg [HIST_BIN_W-1:0] clear_idx;

  always @(posedge aclk) begin
    if (!aresetn) begin
      t0_reg       <= 64'd0;
      t1_reg       <= 64'd0;
      delta_reg    <= 32'd0;
      min_delta    <= 32'h7FFFFFFF;
      max_delta    <= 32'd0;
      sum_delta    <= 64'd0;
      count_delta  <= 64'd0;
      drop_cnt     <= 32'd0;
      overflow_cnt <= 32'd0;
      for (i = 0; i < TYPE_BINS; i = i + 1)
        type_cnt[i] <= 32'd0;
      // Pipeline registers
      delta64_r   <= 64'd0;
      bucket_r    <= {HIST_BIN_W{1'b0}};
      overflow_r  <= 1'b0;
      msg_type_r  <= 4'd0;
      completion_r <= 1'b0;
      ingress_r   <= 1'b0;
      hist_rdata  <= 32'd0;
      type_rdata  <= 32'd0;
      completion_r2 <= 1'b0;
      completion_r3 <= 1'b0;
      completion_r4 <= 1'b0;
      bucket_r3     <= {HIST_BIN_W{1'b0}};
      hist_wdata_r  <= 32'd0;
      bucket_r2     <= {HIST_BIN_W{1'b0}};
      overflow_r2   <= 1'b0;
      clear_busy    <= 1'b0;
      clear_idx     <= {HIST_BIN_W{1'b0}};
      hist_we_r     <= 1'b0;
      hist_waddr_r  <= {HIST_BIN_W{1'b0}};
      hist_wd_r     <= 32'd0;
    end else if (stats_reset_wr) begin
      // Reset statistics only (not the timestamp counter or enable).
      // Takes priority over normal operation even if enable was just set.
      t0_reg       <= 64'd0;
      t1_reg       <= 64'd0;
      delta_reg    <= 32'd0;
      min_delta    <= 32'h7FFFFFFF;
      max_delta    <= 32'd0;
      sum_delta    <= 64'd0;
      count_delta  <= 64'd0;
      drop_cnt     <= 32'd0;
      overflow_cnt <= 32'd0;
      for (i = 0; i < TYPE_BINS; i = i + 1)
        type_cnt[i] <= 32'd0;
      // Pipeline registers
      delta64_r   <= 64'd0;
      bucket_r    <= {HIST_BIN_W{1'b0}};
      overflow_r  <= 1'b0;
      msg_type_r  <= 4'd0;
      completion_r <= 1'b0;
      ingress_r   <= 1'b0;
      hist_rdata  <= 32'd0;
      type_rdata  <= 32'd0;
      completion_r2 <= 1'b0;
      completion_r3 <= 1'b0;
      completion_r4 <= 1'b0;
      bucket_r3     <= {HIST_BIN_W{1'b0}};
      hist_wdata_r  <= 32'd0;
      bucket_r2     <= {HIST_BIN_W{1'b0}};
      overflow_r2   <= 1'b0;
      // Start the histogram clear scan: one entry per cycle, 256 cycles.
      clear_busy    <= 1'b1;
      clear_idx     <= {HIST_BIN_W{1'b0}};
      hist_we_r     <= 1'b0;
      hist_waddr_r  <= {HIST_BIN_W{1'b0}};
      hist_wd_r     <= 32'd0;
    end else if (clear_busy) begin
      // Histogram clear scan.  Runs independently of `enable`; stats capture
      // is held idle until it finishes.  Drive the registered write port
      // with (clear_idx, 0); the array write itself happens in the single
      // write-port statement at the bottom of this block.
      hist_we_r    <= 1'b1;
      hist_waddr_r <= clear_idx;
      hist_wd_r    <= 32'd0;
      if (clear_idx == HIST_BINS - 1)
        clear_busy <= 1'b0;
      else
        clear_idx <= clear_idx + 1'b1;
      completion_r  <= 1'b0;
      completion_r2 <= 1'b0;
      completion_r3 <= 1'b0;
      completion_r4 <= 1'b0;
      bucket_r3     <= {HIST_BIN_W{1'b0}};
      hist_wdata_r  <= 32'd0;
      ingress_r     <= 1'b0;
    end else if (enable_reg) begin
        // ---- Stage 1: capture event context, issue reads ----------------

        // US2: capture t0 at ingress.
        //
        // ingress_r is ingress_valid delayed one cycle (it also drives the
        // per-type counter below).  Capturing through the register keeps the
        // 64-bit flop CE off the combinational ingress_valid net — that path
        // (3 LUT levels in itch_parse + a 64-load CE fan-out) was the 200 MHz
        // critical path at WNS -0.022 ns.  The timestamp counter advanced by
        // exactly one count meanwhile, so subtracting one count recovers the
        // exact ingress time; measured deltas are unchanged.
        if (ingress_r) begin
          t0_reg <= timestamp_counter - 64'd1;
        end
        // Register msg_type for stage 2 type_cnt update
        ingress_r  <= ingress_valid;
        msg_type_r <= msg_type;

        // US2: capture t1 at completion and register the raw delta.  This
        // ends the 64-bit subtractor at delta64_r; nothing downstream of the
        // subtractor is evaluated in this cycle.
        if (completion_valid) begin
          t1_reg    <= timestamp_counter;
          delta64_r <= delta_w;
        end
        completion_r <= completion_valid;


        // ---- Stage 2: derive bucket/overflow/min/max from delta64_r -----
        // delta64_r is a register, so every path here is register-to-register
        // and short.
        if (completion_r) begin
          delta_reg <= delta64_r[31:0];

          // Update min/max from the results computed one stage earlier.
          // Round 201: compare and use in the SAME cycle, reading the same delta64_r. The registered
          // compares (gt_max_r / lt_min_r) were consumed one cycle after they were computed, so the final
          // arrival - the only one that matters for a max - was always missed. Costs the 32-bit compare on
          // the enable path, which is what round 165 bought its timing with; a build must re-check WNS.
          if (count_delta == 64'd0 || delta64_r[31:0] < min_delta)
            min_delta <= delta64_r[31:0];
          if (delta64_r[31:0] > max_delta)
            max_delta <= delta64_r[31:0];

          // Update sum/count
          sum_delta   <= sum_delta + delta64_r[31:0];
          count_delta <= count_delta + 64'd1;

          // Bucket and overflow for the histogram pipeline
          bucket_r   <= bucket_idx;
          overflow_r <= delta_overflow;
        end

        // ---- Stage 3: histogram read with a registered address ---------
        // bucket_r is a register, so this is register → LUTRAM → register.
        hist_rdata    <= hist[bucket_r];
        completion_r2 <= completion_r;   // bucket_r is valid this cycle
        bucket_r2     <= bucket_r;
        overflow_r2   <= overflow_r;

        // Combinational type_cnt read (16-entry register file, short path)
        type_rdata <= type_cnt[msg_type];

        // ---- Stage 4: increment ----------------------------------------
        // Keep the 32-bit incrementer off the LUTRAM write-data path:
        // registering the result first makes both halves register-to-register.
        completion_r3 <= completion_r2;
        bucket_r3     <= bucket_r2;
        hist_wdata_r  <= hist_rdata + 32'd1;
        if (completion_r3 && overflow_r2)
          overflow_cnt <= overflow_cnt + 32'd1;

        // ---- Stage 5: write back ---------------------------------------
        // completion_r4 marks the cycle where (bucket_r3, hist_wdata_r) is
        // valid; drive the registered write port, which the RAM takes on
        // the following edge (see the single write statement below).
        completion_r4 <= completion_r3;
        hist_we_r     <= completion_r4;
        hist_waddr_r  <= bucket_r3;
        hist_wd_r     <= hist_wdata_r;

        if (ingress_r) begin
          // Write back per-type counter (registered type, registered data)
          type_cnt[msg_type_r] <= type_rdata + 32'd1;
        end
      end

      // Single write site for the histogram (one write port, so this keeps
      // the LUTRAM inference template clean).  hist_we_r/waddr/wd are
      // registers, so this path is register -> RAM, not mux -> RAM.
      if (hist_we_r)
        hist[hist_waddr_r] <= hist_wd_r;
    end

  // ----------------------------------------------------------------------
  // AXI4-Lite register slave
  // ----------------------------------------------------------------------

  // ---- write channel --------------------------------------------------

  assign s_axi_awready = wr_fire;
  assign s_axi_wready  = wr_fire;

  always @(posedge aclk) begin
    if (!aresetn) begin
      b_valid    <= 1'b0;
      enable_reg <= 1'b0;
      ctrl_wr_r  <= 1'b0;
      ctrl_en_r  <= 1'b0;
      ctrl_srst_r<= 1'b0;
    end else begin
      // Capture CTRL writes once; the stats block consumes the registered
      // copy (see the comment above stats_reset_wr).
      ctrl_wr_r <= wr_fire && (s_axi_awaddr[11:2] == ADDR_CTRL) &&
                   s_axi_wstrb[0];
      if (wr_fire) begin
        ctrl_en_r   <= s_axi_wdata[0];
        ctrl_srst_r <= s_axi_wdata[1];
      end
      if (ctrl_wr_r)
        enable_reg <= ctrl_en_r;
      if (wr_fire) begin
        b_valid <= 1'b1;
      end else if (s_axi_bvalid && s_axi_bready) begin
        b_valid <= 1'b0;
      end
    end
  end

  assign s_axi_bvalid = b_valid;
  assign s_axi_bresp  = 2'b00;

  // ---- read channel ---------------------------------------------------
  // The read address is registered before the data mux/case.  Feeding
  // s_axi_araddr straight into the mux made the PS7 -> interconnect ->
  // ts_hist route part of the read path (2 logic levels + 4.7 ns route).
  // A one-cycle read latency is allowed by AXI4-Lite.
  reg        rd_pending;
  reg [11:0] araddr_r;
  wire       rd_fire = s_axi_arvalid && !r_valid && !rd_pending;
  assign s_axi_arready = rd_fire;

  // Combinational read mux for histogram & type counters, driven by the
  // registered address.
  wire [9:0] rd_word_addr = araddr_r[11:2];
  wire [31:0] hist_rd  = (rd_word_addr >= ADDR_HIST_BASE &&
                          rd_word_addr < ADDR_HIST_BASE + HIST_BINS) ?
                         hist[rd_word_addr - ADDR_HIST_BASE] : 32'd0;
  wire [31:0] type_rd  = (rd_word_addr >= ADDR_TYPE_BASE &&
                          rd_word_addr < ADDR_TYPE_BASE + TYPE_BINS) ?
                         type_cnt[rd_word_addr - ADDR_TYPE_BASE] : 32'd0;

  always @(posedge aclk) begin
    if (!aresetn) begin
      r_valid    <= 1'b0;
      r_data     <= 32'd0;
      rd_pending <= 1'b0;
      araddr_r   <= 12'd0;
    end else if (rd_fire) begin
      rd_pending <= 1'b1;
      araddr_r   <= s_axi_araddr;
    end else if (rd_pending) begin
      rd_pending <= 1'b0;
      r_valid    <= 1'b1;
      case (rd_word_addr)
          ADDR_CTRL:     r_data <= {30'b0, stats_reset_pending, enable_reg};
          ADDR_T0_LO:    r_data <= t0_reg[31:0];
          ADDR_T0_HI:    r_data <= t0_reg[63:32];
          ADDR_T1_LO:    r_data <= t1_reg[31:0];
          ADDR_T1_HI:    r_data <= t1_reg[63:32];
          ADDR_DELTA:    r_data <= delta_reg;
          ADDR_MIN:      r_data <= min_delta;
          ADDR_MAX:      r_data <= max_delta;
          ADDR_SUM_LO:   r_data <= sum_delta[31:0];
          ADDR_SUM_HI:   r_data <= sum_delta[63:32];
          ADDR_COUNT_LO: r_data <= count_delta[31:0];
          ADDR_COUNT_HI: r_data <= count_delta[63:32];
          default: begin
            if (rd_word_addr >= ADDR_HIST_BASE &&
                rd_word_addr < ADDR_HIST_BASE + HIST_BINS)
              r_data <= hist_rd;
            else if (rd_word_addr >= ADDR_TYPE_BASE &&
                     rd_word_addr < ADDR_TYPE_BASE + TYPE_BINS)
              r_data <= type_rd;
            else if (rd_word_addr == ADDR_DROP_CNT)
              r_data <= drop_cnt;
            else if (rd_word_addr == ADDR_OVERFLOW)
              r_data <= overflow_cnt;
            else if (rd_word_addr == ADDR_TSNOW)
              r_data <= timestamp_counter[31:0];
            else
              r_data <= 32'd0;
          end
        endcase
    end else if (s_axi_rvalid && s_axi_rready) begin
      r_valid <= 1'b0;
    end
  end

  assign s_axi_rvalid = r_valid;
  assign s_axi_rdata  = r_data;
  assign s_axi_rresp  = 2'b00;

endmodule
