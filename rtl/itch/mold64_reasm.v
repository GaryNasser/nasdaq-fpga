// mold64_reasm: MoldUDP64 depacketizer with sequence-gap detection.
//
// Input  : MoldUDP64 packets on S_AXIS (64-bit AXI-Stream).
//          NOTE: TLAST marks packet end, but the design no longer buffers one
//          packet: `pkt_wr_ptr` runs free and TREADY is gated on `fifo_has_room`
//          (see s_can_write), so a DMA transfer may carry any number of packets.
//          An earlier revision aligned to TLAST per packet and overflowed at
//          3+ packets; see docs/bringup-defects.md, the FIFO rewrite section.
//          Packet format: [session:8 bytes][seq:2 BE][count:2 BE]
//          [msg_len:2 BE][msg_body].  Multiple ITCH messages may share one
//          MoldUDP64 packet; each carries its own 2-byte length prefix.
// Output : Reassembled ITCH messages on M_AXIS, one byte per beat.  Each
//          byte beat carries {tkeep=8'h01, tdata[7:0]=byte}; TLAST is
//          asserted on the last byte of each message.  Downstream sees a
//          clean byte stream delimited by TLAST.
//
// Protocol checks:
//   - 8-byte session must match parameter SESSION; mismatch -> packet
//     discarded, error_count++.
//   - 16-bit sequence number vs. expect_seq (reset 16'd1).  If rx_seq >
//     expect_seq -> gap_count++ (detected gap).  expect_seq advances to
//     rx_seq + 1 in all cases.
//   - count field is advisory; actual messages are self-delimiting via
//     their 2-byte length prefix.
//
// Flow control:
//   - S_AXIS TREADY deasserts when a completed packet is buffered but not
//     yet fully parsed (pkt_hold asserted), or when the next packet would
//     overwrite the buffer the parser is about to read (pkt_rx_done).  This
//     provides backpressure to the upstream DMA.
//   - M_AXIS TVALID / TREADY handshake stalls the parser output cleanly.
//
// Stats & control (RO unless noted), AXI4-Lite, offsets frozen:
//   0x00 RX_PACKETS_LO   [31:0] of rx_packets (packets received & parsed)
//   0x04 RX_PACKETS_HI   [63:32]
//   0x08 RX_MESSAGES_LO  [31:0] of rx_messages (messages emitted)
//   0x0C RX_MESSAGES_HI  [63:32]
//   0x10 GAP_COUNT       sequence gaps detected
//   0x14 ERROR_COUNT     session mismatch + malformed / truncated
//   0x18 CTRL            RW bit0=enable (default 0, gates packet acceptance
//                            and parser); bit1=soft_reset (write 1 to clear
//                            counters + FSM; self-clearing)
//
// Architecture: store-forward packet RAM (2^FIFO_AW bytes).  Incoming 64-bit
// S_AXIS beats are written as one 64-bit word per beat into a BRAM (address
// = byte_ptr >> 3).  The parser FSM reads one byte per clock, selecting the
// byte within the 64-bit BRAM word via the low 3 bits of the read pointer.
// A byte-valid handshake accounts for the BRAM's registered read latency.
//
// All multi-byte fields are big-endian (MoldUDP64 / ITCH network order):
// the first byte received is the MSB.

`timescale 1ns / 1ps


module mold64_reasm #(

    parameter [63:0] SESSION  = 64'h4E41534441513031,  // "NASDAQ01"
    parameter        FIFO_AW = 12                      // 4096-byte packet RAM (> 2 MTU)
)(
    input  wire        aclk,
    input  wire        aresetn,

    // AXI4-Lite slave (stats + control)
    input  wire [4:0]  s_axi_awaddr,
    input  wire [2:0]  s_axi_awprot,
    input  wire        s_axi_awvalid,
    output wire        s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [4:0]  s_axi_wstrb,
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

    // AXI-Stream slave: MoldUDP64 packets in (64-bit wide, TLAST = pkt end)
    input  wire [63:0] s_axis_tdata,
    input  wire [7:0]  s_axis_tkeep,
    input  wire        s_axis_tvalid,
    output wire        s_axis_tready,
    input  wire        s_axis_tlast,

    // AXI-Stream master: reassembled ITCH messages out (1 byte / beat)
    output wire [63:0] m_axis_tdata,
    output wire [7:0]  m_axis_tkeep,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast
);

  // Largest depth that can legitimately be outstanding. A larger value means
  // the pointers are inconsistent (a reader that overran), so the read gate
  // closes instead of letting the FSM consume stale RAM.
  localparam [FIFO_AW-1:0] ERR_MAX_DEPTH = {FIFO_AW{1'b1}};

  // Both FIFO byte counters are one bit wider than an index. With
  // FIFO_AW bits a true gap of 4096 subtracts to 0, so a completely full
  // FIFO is indistinguishable from an empty one; the extra bit carries
  // that lap so flow control can actually see the fill.
  //
  // They are declared here, above the flow-control logic, because that
  // logic uses them: Verilog requires declaration before use and the
  // file previously declared them further down.
  reg  [FIFO_AW:0] bytes_accepted;
  reg  [FIFO_AW:0] bytes_committed;
  reg              soft_reset_r;
  wire             soft_reset_pulse;
  wire             s_wr_fire;


  // ----------------------------------------------------------------------
  // FSM state encoding
  // ----------------------------------------------------------------------
  localparam [4:0] ST_IDLE        = 5'd0;   // packet RAM empty, waiting
  localparam [4:0] ST_SESSION0    = 5'd1;   // collect session byte 0 (MSB)
  localparam [4:0] ST_SESSION1    = 5'd2;
  localparam [4:0] ST_SESSION2    = 5'd3;
  localparam [4:0] ST_SESSION3    = 5'd4;
  localparam [4:0] ST_SESSION4    = 5'd5;
  localparam [4:0] ST_SESSION5    = 5'd6;
  localparam [4:0] ST_SESSION6    = 5'd7;
  localparam [4:0] ST_SESSION7    = 5'd8;   // collect session byte 7 (LSB)
  localparam [4:0] ST_SESSION_CHK = 5'd18;  // compare registered session bytes
  localparam [4:0] ST_SEQ_HI      = 5'd9;   // seq number high byte (MSB)
  localparam [4:0] ST_SEQ_LO      = 5'd10;  // seq number low byte
  localparam [4:0] ST_SKIP_CNT0   = 5'd11;  // skip 2-byte count field (advisory)
  localparam [4:0] ST_SKIP_CNT1   = 5'd12;
  localparam [4:0] ST_MLEN_HI     = 5'd13;  // message length high byte (MSB)
  localparam [4:0] ST_MLEN_LO     = 5'd14;  // message length low byte
  localparam [4:0] ST_EMIT        = 5'd15;  // emit message body bytes
  localparam [4:0] ST_EMIT_LEN_HI = 5'd16;  // emit msg_len[15:8] (length prefix)
  localparam [4:0] ST_EMIT_LEN_LO = 5'd17;  // emit msg_len[7:0] (length prefix)

  // ----------------------------------------------------------------------
  // Control register (declared early -?referenced by S_AXIS write logic
  // above and AXI-Lite write logic below).
  // ----------------------------------------------------------------------
  reg enable;  // CTRL bit0 -?gates packet acceptance & parser

  // ----------------------------------------------------------------------
  // Packet RAM (64-bit wide store-and-forward buffer, inferred as BRAM)
  // ----------------------------------------------------------------------
  // One S_AXIS beat (8 bytes) maps to one 64-bit RAM entry.  Write address
  // is the beat index (byte_ptr >> 3); read address is the same.  The
  // parser's byte-level write pointer tracks valid bytes so stale bytes
  // from non-full last beats are never read.  A single 64-bit write port
  // + registered read lets Vivado infer a real BRAM36 (512 x 64 bits =
  // 4096 bytes) instead of dissolving into 4097 registers + 32K-bit muxes
  // (which OOMs the synthesizer).
  localparam FIFO_AW_BEAT = FIFO_AW - 3;  // 9 bits -> 512 entries
  (* ram_style = "block" *) reg [63:0] pkt_ram [0:(1 << FIFO_AW_BEAT) - 1];

  // Byte-write-enable staging for the packet RAM.
  //
  // Each byte of an incoming 64-bit beat carries its own write enable and
  // address, computed from the byte's position mod 2^FIFO_AW.  This lets one
  // source beat commit into two different RAM words when it straddles a word
  // boundary, which is the normal case once packets no longer start at 0.
  reg                    pkt_ram_we  [0:7];
  reg [FIFO_AW_BEAT-1:0] pkt_ram_wa  [0:7];
  reg [7:0]              pkt_ram_wd  [0:7];
  reg [FIFO_AW-1:0] pkt_wr_ptr;   // byte write index, free-running
  reg [FIFO_AW-1:0] pkt_rd_ptr;   // byte read index, free-running
  // Latched length of the packet whose TLAST was just seen.
  //
  // pkt_wr_ptr is written by the same always block that sees s_pkt_last, so
  // on the TLAST cycle pkt_wr_ptr still holds the *pre-last-beat* value and
  // does not include the final beat's bytes.  The FSM's claim in ST_IDLE can
  // fire on the very next cycle (pkt_rx_done is set at TLAST), which would
  // capture a packet length short by up to 8 bytes: the FSM then finishes the
  // packet early, the remaining beats of the *next* packet are misread as
  // part of this one, and the module wedges.
  //
  // Latching the post-update length here removes the race entirely: the claim
  // consumes pkt_len_latched, which already includes the TLAST beat.

  reg                pkt_rx_done; // set by write path on TLAST; cleared by FSM
                                   // when claiming the buffer.  While set, blocks
                                   // S_TREADY so the next packet cannot overwrite
                                   // the buffer the parser is about to read.
  reg                pkt_rx_active; // a packet reception is in progress (beats
                                     // arriving, TLAST not yet seen)

  // ----------------------------------------------------------------------
  // Pack valid byte lanes from a 64-bit S_AXIS beat into the packet RAM.
  // ----------------------------------------------------------------------
  // The whole 64-bit beat is written in one clock at address wr_ptr>>3.
  // tkeep determines how many bytes are valid; the parser's write pointer
  // advances by the valid-byte count so it never reads stale RAM contents.
  //
  // TREADY must depend ONLY on the receiver's own state -?never on TVALID.
  // The original form was
  //     wire s_can_write  = enable && s_axis_tvalid && !pkt_hold && !pkt_rx_done;
  //     assign s_axis_tready = s_can_write;
  // which feeds TVALID into TREADY.  That is an AXI-Stream protocol violation
  // and it creates a combinational TVALID<->TREADY path with the master: on
  // hardware (AXI DMA MM2S) the handshake then resolved differently than in
  // simulation (the testbench drives TVALID from a reg and never sees the
  // hazard), and only every other beat was committed -?a 1463-byte packet
  // ended with pkt_wr_ptr=731, exactly half.  TREADY is now purely a function
  // of readiness, and firing is TVALID && TREADY.
  //
  // The buffer is single-packet: while a completed packet awaits the FSM
  // (pkt_rx_done) or the FSM is parsing (pkt_hold), TREADY is low and the
  // DMA is back-pressured.  That is the intended steady-state throttle.
  //
  // CAPACITY GUARD.  pkt_rx_done is registered, so it rises one cycle AFTER
  // the TLAST beat is accepted.  AXI DMA MM2S can present a beat every cycle,
  // so the first beats of the NEXT packet can already be accepted in that
  // window -?and in a long transfer a later packet's TLAST can arrive before
  // the FSM ever claims, letting pkt_wr_ptr free-run until it wraps the
  // 12-bit counter.  Measured on hardware: 1 and 2 packets (1463/2920 B)
  // transferred correctly because they fit the 4096-byte RAM, while 3+
  // packets (4386 B) wrapped (pkt_wr_ptr = 290 = 4386 mod 4096) and the
  // module wedged with bytes_rem stuck at 2040.
  //
  // TREADY is therefore also dropped once the RAM is within one maximum beat
  // of full.  A packet larger than the RAM cannot be buffered anyway, so this
  // turns "silent wrap and wedge" into clean back-pressure.  The high-water
  // mark is RAM-8 so a single 64-bit beat can always still land.
  //
  // ==========================================================================
  // BYTE-FIFO FLOW CONTROL
  // ==========================================================================
  // The packet RAM is a circular byte FIFO, not a single-packet buffer.  The
  // previous design stored exactly one packet and relied on AXI TLAST to
  // delimit it; on a continuous DMA stream (3+ packets, >4096 B) that
  // overran the pointer and wedged the module -?see docs/bringup-defects.md.
  // The FSM never needed TLAST: it walks the MoldUDP64 structure
  // (session -> seq -> count -> {len, body}*) from the byte contents, so
  // packets delimit themselves and any number may sit back-to-back.
  //
  //   pkt_wr_ptr : byte write index, free-running (wraps at 2^FIFO_AW)
  //   pkt_rd_ptr : byte read index,  free-running (wraps at 2^FIFO_AW)
  //   bytes_in   : occupancy, 0 .. 2^FIFO_AW
  // (fifo_room was dead once TREADY moved to the registered depth guard)
  // Measured on the COMMITTED pointer, not the accepted one: accepted
  // counts beats as they arrive, but their bytes only reach the RAM when
  // the word is committed two cycles later, so a guard built on it lets a
  // beat through before its data exists (measured MAXDEPTH=4127 against a
  // 4096-byte RAM). Committed never leads the data.
  //
  // 2^FIFO_AW is the RAM size, built by shifting so it stays correct if
  // FIFO_AW changes - a first attempt used all-ones of the counter width
  // (8191) and the guard was effectively open.
  // 2^FIFO_AW, as a plain shift into a (FIFO_AW+1)-bit field.
  //
  // WAS: ({(FIFO_AW+1){1'b0}} >> 1) | ({(FIFO_AW+1){1'b1}} << (FIFO_AW - 1))
  // which evaluates to 4096 | 6144 = 6144, not 4096.  The all-ones term is
  // 8191, shifted left by FIFO_AW-1 and truncated to FIFO_AW+1 bits it becomes
  // 0x1800, so the OR turned a 4096-byte FIFO into a 6144-byte one.  The room
  // guard then let the writer reach 6080 bytes in a 4096-byte RAM and lap the
  // reader, overwriting unread data whenever the sink stalled long enough for
  // the FIFO to exceed 4096 bytes - measured as a hard cliff between a 96-cycle
  // and a 128-cycle downstream stall.  This is what lost 19139 bytes in the
  // full chain while every isolated test passed.
  localparam [FIFO_AW:0] FIFO_BYTES = {{FIFO_AW{1'b0}}, 1'b1} << FIFO_AW;
  wire [FIFO_AW:0] fifo_wr_depth  = bytes_committed - {{FIFO_AW{1'b0}}, pkt_rd_ptr};
  // fifo_not_empty is declared next to fifo_available below, which is the

  // The room comparison is REGISTERED.
  //
  // Left combinational it became the worst path in the design - measured
  // WNS -2.160 ns with a 7.075 ns data path (71% route), running
  // bytes_committed -> subtractor -> comparator -> TREADY -> hold_data load
  // enable -> the RAM write address. Registering it puts the subtractor and
  // comparator behind a flop so TREADY drives the fanout directly.
  //
  // Occupancy changes by one byte per reader beat and at most one beat per
  // writer cycle, so a cycle of latency is harmless given the reserve below.
  reg fifo_has_room_r;
  always @(posedge aclk) begin
    if (!aresetn || soft_reset_pulse)
      fifo_has_room_r <= 1'b0;
    else
      // 64-byte reserve: a beat plus the commit pipeline plus one cycle for
      // this register, so the extra latency cannot let a beat slip past.
      fifo_has_room_r <= (fifo_wr_depth < (FIFO_BYTES - 9'd64));
  end

  wire fifo_has_room = fifo_has_room_r;

  wire s_can_write = enable && fifo_has_room;
  assign s_axis_tready = s_can_write;

  assign s_wr_fire = s_axis_tvalid && s_axis_tready;

  // Number of valid bytes in this beat (popcount of tkeep).
  //
  // All seven s_axis_tkeep bits are 1-bit selects, and Verilog sizes an
  // expression by its widest operand, so 1 + tk[1] + ... + tk[7] would be
  // evaluated in 1 bit and truncate modulo 2.  Every full beat would then
  // advance the pointer by 0 or 1 instead of 8, which is exactly the
  // hardware symptom: a 1463-byte packet reached pkt_wr_ptr = 731 (half) and
  // the parser then ran off the end of the packet.  Signal names are forced
  // to 4 bits (16'd / 4'd) so the sum is carried at full width.
  wire [3:0] tkeep_cnt = 4'd1 + {3'd0, s_axis_tkeep[1]} + {3'd0, s_axis_tkeep[2]}
                      + {3'd0, s_axis_tkeep[3]} + {3'd0, s_axis_tkeep[4]}
                      + {3'd0, s_axis_tkeep[5]} + {3'd0, s_axis_tkeep[6]}
                      + {3'd0, s_axis_tkeep[7]};

  // ----------------------------------------------------------------------
  // Write-alignment stage
  // ----------------------------------------------------------------------
  // AXI beats arrive 8 bytes at a time but stream boundaries do not align to
  // the word-addressed RAM, and a dynamic bit-slice is not a legal assignment
  // target in Verilog. This stage therefore accumulates bytes in a holding
  // register and commits only COMPLETE words, at static lanes 0..7.
  //
  // The stream is continuous: the holding register carries bytes across
  // packet boundaries rather than being flushed per packet. An earlier design
  // flushed-and-padded at every TLAST, which inserted padding into the
  // address space; a later one left the pointer unadvanced so the next
  // packet's beat overwrote the previous packet's tail bytes. Keeping one
  // continuous byte-addressed stream avoids both.
  //
  //   pkt_wr_ptr : BYTE granular, advances by beat_bytes (never skips)
  //   hold_data  : bytes not yet committed to a word
  //   hold_n     : how many (0..15; one beat can complete a word and spill)
  reg [127:0] hold_data;
  reg [3:0]   hold_n;

  wire [3:0]  beat_bytes = tkeep_cnt;                // valid lanes in this beat
  // hold_data holds its bytes starting at lane 0, so it must be ZERO
  // EXTENDED into the 128-bit field, not shifted up.  The previous form
  // ({hold_data, 64'd0}) placed the held bytes at bits [191:64] while the
  // committed word is read from merged[63:0], so bytes carried across a packet
  // boundary were silently dropped from the word they belonged to.
  wire [131:0] merged    = {{4{1'b0}}, hold_data[127:0]}
                           | ({128'd0, s_axis_tdata} << (hold_n * 8));
  wire [4:0]  avail      = {1'b0, hold_n} + {1'b0, beat_bytes};
  wire        word_ready = s_wr_fire && (avail >= 5'd8);

  // ----------------------------------------------------------------------
  // Commit stage: REGISTERED word, address and enable
  // ----------------------------------------------------------------------
  // Left combinational, `commit_word` drove the RAM write-data input through
  // the BRAM bank muxing and became the worst path in the design:
  //
  //     pkt_wr_ptr -> ... -> pkt_ram/RAMC/I
  //     5.705 ns, of which only 1.240 ns is logic (78% is route)
  //
  // Registering it puts a flop directly in front of the RAM data input. The
  // cost is one cycle between accepting a beat and committing its word, which
  // nothing relies on being immediate: the reader is bounded by
  // bytes_committed, which comes from this same stage and is delayed with it.
  reg [63:0]        cm_word;
  reg [FIFO_AW-1:0] cm_addr;
  reg               cm_valid;
  reg [127:0]       cm_rem_data;
  reg [3:0]         cm_rem_n;

  wire [63:0]  commit_word_comb = merged[63:0];      // full word to write
  wire [127:0] rem_data_comb    = merged[127:64];    // carried forward
  wire [3:0]   rem_n_comb       = avail[3:0] - 4'd8; // 0..7 after one commit

  // The committing beat's byte position in the continuous stream.
  wire [FIFO_AW-1:0] commit_byte_addr_comb =
      pkt_wr_ptr - {{(FIFO_AW-4){1'b0}}, hold_n};

  always @(posedge aclk) begin
    if (!aresetn || soft_reset_pulse) begin
      cm_valid <= 1'b0;
      cm_word  <= 64'd0;
      cm_addr  <= {FIFO_AW{1'b0}};
      cm_rem_data <= 128'd0;
      cm_rem_n    <= 4'd0;
    end else begin
      cm_valid <= word_ready;
      if (word_ready) begin
        cm_word     <= commit_word_comb;
        cm_addr     <= commit_byte_addr_comb;
        cm_rem_data <= rem_data_comb;
        cm_rem_n    <= rem_n_comb;
      end
    end
  end

  // Names used by the rest of the design now refer to the registered stage.
  wire [63:0]        commit_word      = cm_word;
  wire [FIFO_AW-1:0] commit_byte_addr = cm_addr;
  wire               commit_fire      = cm_valid;
  wire [127:0]       rem_data         = cm_rem_data;
  wire [3:0]         rem_n            = cm_rem_n;

  // Byte-granular count of real bytes accepted from S_AXIS.  Padding written
  // by a tail flush is deliberately NOT counted, so the reader can never step
  // past the real data.  This is the authoritative "how much may be read"
  // pointer; the RAM's word-granular write pointer is an internal detail.
  // FIFO_AW bits so it wraps with the other indices (see the note above
  // fifo_occupancy): an index wider than the address space silently
  // corrupts occupancy once the stream passes 2^FIFO_AW bytes.
  // (declared above, beside the parameter block)
  // Single driver, soft reset folded in (see note on bytes_committed).
  always @(posedge aclk) begin
    if (!aresetn || soft_reset_pulse)
      bytes_accepted <= {(FIFO_AW+1){1'b0}};
    else if (s_wr_fire)
      bytes_accepted <= bytes_accepted + { {(FIFO_AW-3){1'b0}}, beat_bytes };
  end

  // Bytes that have actually reached the RAM.  This -?not bytes_accepted -?is
  // what the reader may consume: the holding register can retain up to 7 bytes
  // that are accepted but not yet written, so bounding the reader by
  // bytes_accepted let it read up to 7 bytes ahead of the real data and see
  // stale RAM (manifesting as failed session comparisons, err=6).
  //
  // A word commit publishes 8 bytes at once; since the pointer is byte
  // granular, the committed position after a commit is wr rounded up to the
  // word that was just written.
  reg  tail_pending;
  // Do NOT publish while a registered commit is pending. The RAM write block
  // is `if (commit_fire) ... else if (tail_publish) ...`, so when both are
  // asserted the commit wins and the TAIL WRITE IS SILENTLY DROPPED while
  // bytes_committed still advances past those bytes. That truncated the last
  // packet of a run (measured: 39/40 packets, err=1, only with the registered
  // commit stage). tail_pending is cleared only by tail_publish, so gating here
  // simply defers the publish by the commit's one cycle.
  wire tail_publish = !s_wr_fire && tail_pending && (hold_n != 4'd0) && !cm_valid;

  always @(posedge aclk) begin
    if (!aresetn || soft_reset_pulse)
      tail_pending <= 1'b0;
    else if (s_wr_fire)
      // Set ONLY by a beat carrying TLAST.  This used to be set by every
      // beat, so any ordinary gap between beats fired tail_publish
      // mid-stream: a partial word was published and bytes_committed jumped
      // to pkt_wr_ptr although only hold_n of its lanes had been written.
      // The reader could then read lanes that do not exist and got stale
      // RAM, showing up as a session mismatch at a position that depended
      // on writer timing - which is why it only appeared for longer
      // streams (88 packets passed, 89 failed).
      tail_pending <= s_axis_tlast;
    else if (tail_publish)
      tail_pending <= 1'b0;
  end

  // Lane enables for publishing a partial tail word: only the lanes that
  // hold real bytes are written.
  wire [7:0] tail_we = (8'd1 << hold_n) - 8'd1;

  // While it was one bit wider it kept growing past 4095 after the first
  // wrap, the comparison with the 12-bit read pointer stopped matching, and
  // every packet after 4096 bytes was lost (measured: 20 packets = 1000 B
  // parsed perfectly; 100 packets = 5000 B collapsed to 14).
  // (declared above, beside the parameter block)
  // Single driver: the soft-reset clear is folded in below rather than being a
  // second assignment in the shared soft-reset block. Two always blocks driving
  // one reg is a multiple-driver error (DRC MDRV-1) that simulation hides.
  always @(posedge aclk) begin
    if (!aresetn || soft_reset_pulse)
      bytes_committed <= {(FIFO_AW+1){1'b0}};
    else if (commit_fire)
      // commit_byte_addr is the word-aligned start of the word just written,
      // so the word end is commit_byte_addr + 8 (truncation gives the wrap).
      bytes_committed <= {1'b0, commit_byte_addr} + 9'd8;
    else if (tail_publish)
      bytes_committed <= {1'b0, pkt_wr_ptr};
  end

  wire        s_pkt_last = s_wr_fire && s_axis_tlast;

  // Trailing partial word.  When the stream goes quiet with fewer than 8 bytes
  // held, those bytes are still real data and must become readable.  They are
  // published with a lane mask covering only the valid lanes, so no padding
  // enters the address space and the pointer does not move.
  // ----------------------------------------------------------------------
  // SINGLE RAM write port
  // ----------------------------------------------------------------------
  // This used to be two assignments to the same array with different address
  // expressions - one for the registered commit, one for the tail publish.
  // Two write addresses on one memory force Vivado to synthesise a
  // read-modify-write inside the BRAM, which became the worst path in the
  // design:
  //
  //     pkt_wr_ptr -> RAM read port -> LUT6 -> MUXF7 -> LUT6 -> RAM data
  //     4.889 ns, 74.6% route
  //
  // Merging them into a single muxed write gives a true one-write-port memory.
  // The two sources are mutually exclusive by construction: tail_publish is
  // gated with !cm_valid, so a commit and a tail publish cannot coincide.
  wire [63:0] tail_mask = {
    {8{tail_we[7]}}, {8{tail_we[6]}}, {8{tail_we[5]}}, {8{tail_we[4]}},
    {8{tail_we[3]}}, {8{tail_we[2]}}, {8{tail_we[1]}}, {8{tail_we[0]}}
  };

  wire                ram_we  = commit_fire | tail_publish;
  wire [FIFO_AW-1:0]  ram_adr = commit_fire ? commit_byte_addr : pkt_wr_ptr;
  wire [63:0]         ram_dat = commit_fire ? commit_word
                                            : (hold_data & tail_mask);

  always @(posedge aclk) begin
    if (ram_we)
      pkt_ram[ram_adr[FIFO_AW-1:3]] <= ram_dat;
  end

  // TLAST beat: packet complete

  // The write address is the free-running write pointer: it wraps inside the
  // RAM, so consecutive packets continue from wherever the previous one left
  // off and no per-packet realignment is needed.
  wire [FIFO_AW-1:0]      wr_ptr_eff   = pkt_wr_ptr;
  wire [FIFO_AW_BEAT-1:0] wr_beat_addr = pkt_wr_ptr[FIFO_AW-1:3];



  // Bytes contributed by the beat currently being accepted -?the same value
  // the pkt_wr_ptr update below adds.  Factored out so pkt_wr_ptr and
  // pkt_len_latched are guaranteed to use one expression.
  wire [FIFO_AW-1:0] next_beat_bytes = { {FIFO_AW-4{1'b0}}, tkeep_cnt };

  // Increment applied to the write pointer for this beat.  Equal to the
  // number of valid lanes; written as an explicit mux so the synthesizer maps
  // the eight legal TKEEP cases to constants instead of a general popcount
  // (cheaper, and it keeps the adder on the critical path to a single carry
  // chain).
  // ----------------------------------------------------------------------
  // Per-byte write address / enable / data
  // ----------------------------------------------------------------------
  // For lane i of the incoming beat:
  //   byte position : (pkt_wr_ptr + i) mod 2^FIFO_AW
  //   RAM word      : position[FIFO_AW-1:3]
  //   lane inside   : position[2:0]
  //   enable        : TKEEP[i]
  // The add's carry is discarded, which gives exactly the modular wrap the
  // circular buffer needs.  A lane is written only if TKEEP marks it valid,
  // so a short final beat never disturbs bytes it does not own.

  wire [FIFO_AW-1:0] pkt_wr_inc =
      (s_axis_tkeep == 8'b00000001) ? {{(FIFO_AW-1){1'b0}}, 1'b1} :
      (s_axis_tkeep == 8'b00000011) ? {{(FIFO_AW-2){1'b0}}, 2'd2} :
      (s_axis_tkeep == 8'b00000111) ? {{(FIFO_AW-3){1'b0}}, 3'd3} :
      (s_axis_tkeep == 8'b00001111) ? {{(FIFO_AW-3){1'b0}}, 3'd4} :
      (s_axis_tkeep == 8'b00011111) ? {{(FIFO_AW-3){1'b0}}, 3'd5} :
      (s_axis_tkeep == 8'b00111111) ? {{(FIFO_AW-3){1'b0}}, 3'd6} :
      (s_axis_tkeep == 8'b01111111) ? {{(FIFO_AW-3){1'b0}}, 3'd7} :
                                       next_beat_bytes;

  always @(posedge aclk) begin
    if (!aresetn || soft_reset_pulse) begin
      pkt_wr_ptr     <= {FIFO_AW{1'b0}};
      pkt_rx_active  <= 1'b0;
      hold_data      <= 128'd0;
      hold_n         <= 4'd0;
    end else if (s_wr_fire) begin
      // --- alignment stage: accumulate bytes, commit complete words -----
      if (word_ready) begin
        // A full word landed: commit it and retain the remainder.
        hold_data <= rem_data_comb;
        hold_n    <= rem_n_comb;
      end else begin
        hold_data <= merged[127:0];
        hold_n    <= avail[3:0];
      end

      // BYTE-granular: the pointer tracks the true stream position and never
      // skips, so committed words always land at the correct address and no
      // byte is overwritten by a later packet.
      pkt_wr_ptr <= pkt_wr_ptr + next_beat_bytes;

      pkt_rx_active <= !s_axis_tlast;
    end
  end


  // ----------------------------------------------------------------------
  // FIFO occupancy
  // ----------------------------------------------------------------------
  // bytes_in is derived purely from how far the two free-running pointers
  // have moved, so it is correct regardless of where packet boundaries fall.
  // Both pointers wrap at 2^FIFO_AW, so modular subtraction gives occupancy
  // directly.  This replaces the TLAST-driven claim/hold/release handshake
  // that wedged the module on multi-packet DMA transfers.
  //
  // WIDTH IS CRITICAL: the subtraction must be performed in exactly FIFO_AW
  // bits and only then zero-extended.  In an assignment Verilog evaluates the
  // RHS at max(LHS,RHS) width, so `bytes_in <= wr - rd` (13-bit LHS) computes
  // in 13 bits and wraps at 8192 instead of 4096: a write pointer one behind
  // the read pointer yields ~8191 rather than 4095, occupancy sails past the
  // RAM size and TREADY/underflow decisions go wrong.  Observed on the first
  // run as bytes_in = 8178.  The explicit truncation below keeps the modular
  // arithmetic at 12 bits.
  // Occupancy is measured from the ONE authoritative byte count, the same
  // value the reader is bounded by.  Deriving it from the word-granular
  // pkt_wr_ptr instead made the two disagree by up to 7 bytes per packet
  // (padding), which showed up as phantom occupancy (bytes_in = 4087),
  // TREADY collapsing and the parser stalling.
  //
  // pkt_wr_ptr remains word granular and is used ONLY to address the RAM
  // write port; it is no longer part of any flow-control decision.
  // Both operands are FIFO_AW bits, so this is a true 12-bit modular
  // difference.  The result is zero-extended into the depth, which is
  // the only value that needs the extra bit (a full FIFO is 4096).
  wire [FIFO_AW-1:0] fifo_occupancy_diff = bytes_accepted - pkt_rd_ptr;
  wire [FIFO_AW:0]   fifo_occupancy      = {1'b0, fifo_occupancy_diff};

  // `bytes_in` is the registered copy used for the TREADY threshold, where a
  // one-cycle lag only costs a little throughput.  The FSM's *consumption*
  // decision must not lag: a stale non-zero reading lets it read one byte past
  // the write pointer, and because the pointers are modular that single
  // over-read looks like ~4000 bytes of occupancy (observed as rd=143 > wr=128
  // and phantom "8178 bytes buffered").  All read-side gating therefore uses
  // this live, unregistered comparison.
  //
  // SAFETY MARGIN: the reader must stay a few bytes BEHIND the writer.  A beat
  // is committed by a registered write and returned by a registered read, so
  // the word covering byte N is only readable a couple of cycles after the
  // writer advanced past it.  Testing wr != rd let the parser read a word in
  // the cycle it was written and observe stale contents; that showed up as the
  // parser burning the first 8 bytes of a packet and starting mid-header (the
  // session bytes read back as 00 02 00 01 instead of NASDAQ01).  Requiring a
  // small separation guarantees the target word has settled.  Cost: 8 bytes of
  // usable capacity out of 4096, which is negligible.
  // A byte is readable once it has been COMMITTED for two cycles: the RAM
  // write is registered by one cycle and the read data by another, so a word
  // written this cycle is not yet observable.  Delaying the write pointer by
  // two cycles expresses exactly that.
  //
  // An earlier attempt used a fixed `occupancy >= 8` margin instead. That is
  // wrong at the tail of a stream: once the writer stops with 7 bytes still
  // buffered, the reader can never reach the threshold and the parser hangs
  // (observed: rd=43, wr=50, bin=7, FSM parked in ST_IDLE).
  // A RAM word is only ever written when COMPLETE (see the write-alignment
  // stage), so a word is either wholly valid or wholly absent and the reader
  // can never observe a partial word.  That removes the straddle hazard that
  // forced lane-aware permission, and a fixed byte margin is unnecessary too
  // (it deadlocked at the tail of a stream).  All that remains is the
  // write -> read pipeline latency, covered by delaying the write pointer by
  // two cycles.
  reg [FIFO_AW-1:0] wr_ptr_d1, wr_ptr_d2;
  always @(posedge aclk) begin
    if (!aresetn || soft_reset_pulse) begin
      wr_ptr_d1 <= {FIFO_AW{1'b0}};
      wr_ptr_d2 <= {FIFO_AW{1'b0}};
    end else begin
      wr_ptr_d1 <= pkt_wr_ptr;
      wr_ptr_d2 <= wr_ptr_d1;
    end
  end

  // The reader may consume exactly the bytes that were really received.  The
  // bound is bytes_accepted delayed to cover the RAM write -> read pipeline;
  // using the raw value would let the reader observe a word before its data
  // has propagated.  Padding never enters this count, so a flushed tail word
  // is readable only up to its real bytes.
  reg [FIFO_AW-1:0] acc_d1, acc_d2;
  always @(posedge aclk) begin
    if (!aresetn || soft_reset_pulse) begin
      acc_d1 <= {FIFO_AW{1'b0}};
      acc_d2 <= {FIFO_AW{1'b0}};
    end else begin
      acc_d1 <= bytes_accepted;
      acc_d2 <= acc_d1;
    end
  end

  wire [FIFO_AW-1:0] fifo_occupancy_live = acc_d2 - pkt_rd_ptr;
  // Consumable only up to the bytes that are actually IN the RAM.
  //
  // This MUST be a positive-depth test, not a pointer inequality. With
  // wrapping pointers `pkt_rd_ptr != bytes_committed` is true both when data
  // is available AND when the reader has overrun the writer, so it cannot
  // tell the two apart. Measured on an 89-packet stream:
  //
  //     AT320 acc=302 wr=302 cmt=296 bin=4079
  //
  // the reader was at byte 320 with the writer only at 302, i.e. 18 bytes
  // past the data, and the depth had underflowed to 4096-17. The FSM then
  // read stale RAM, failed the session compare and lost every remaining
  // packet. Short streams never lost their place, which is why they passed.
  //
  // `available` is the modular distance from the read pointer to the
  // committed pointer, valid because flow control keeps the true gap below
  // the RAM size. It is 0 (empty) when the reader has caught up or overrun.
  wire [FIFO_AW-1:0] fifo_available = bytes_committed - pkt_rd_ptr;
  // The whole 64-bit word that pkt_rd_ptr selects has been written by the producer.
  //
  // Used by ST_IDLE so the FSM never reads a word the producer has not finished writing.
  //
  // TIMING NOTE (round 150): in this combinational form the condition is a 4-bit subtract plus a
  // 12-bit magnitude compare feeding ST_IDLE's state enable, and a rebuild closed at WNS -0.125 ns
  // where the deployed build had +0.042 - the failing path is pkt_rd_ptr_reg[0] -> state_reg[0]/CE.
  // Two cheaper forms were tried and both break measured behaviour:
  //     fifo_available >= 8          sufficient but not necessary; breaks tb_pause_test and
  //                                  tb_pause_sweep because a mid-word packet boundary waits longer
  //     registering this compare     lags pkt_rd_ptr; breaks session_bad, pause_test, pause_sweep
  // **So the fix is functionally correct and does not currently meet 190 MHz.** Resolving that
  // needs a retiming change, not another guard formulation.
  //
  // RETAIMING (round 151): the threshold is at most 8, so only the low four bits of fifo_available can
  // be below it. Testing the upper bits separately confines the magnitude compare to 4 bits:
  //
  //     fifo_available[FIFO_AW-1:4] != 0                 -> at least 16 buffered, always enough
  //     || fifo_available[3:0] >= (8 - pkt_rd_ptr[2:0])  -> the 4-bit compare
  //
  // This is EXACTLY equivalent - checked exhaustively over all 8 lanes x all 4096 available values in
  // tools/derive_form_d.py - and it replaces a 12-bit compare plus a subtractor with an OR reduce and
  // a 4-bit compare, removing eight bits of carry chain from the pkt_rd_ptr -> state enable path.
  wire [3:0] bytes_missing_in_word = 4'd8 - {1'b0, pkt_rd_ptr[2:0]};
  wire word_committed = (fifo_available[FIFO_AW-1:4] != {(FIFO_AW-3){1'b0}})
                        || (fifo_available[3:0] >= bytes_missing_in_word);
  // Debug status bit: the authoritative depth, reported rather than a second
  // separately-maintained copy (the old bytes_in counter is gone).
  wire fifo_not_empty = (fifo_available != {FIFO_AW{1'b0}});
  wire fifo_not_empty_live = (fifo_available != {FIFO_AW{1'b0}})
                             && (fifo_available <= ERR_MAX_DEPTH);

  // ----------------------------------------------------------------------
  // Incremental depth counter
  // ----------------------------------------------------------------------
  // Occupancy MUST NOT be derived as a difference of two wrapped indices.  A
  // 12-bit modular difference cannot represent a full 4096: gap 0 (empty) and
  // gap 4096 (full) both read as 0, and a writer that has lapped the reader
  // looks like it is BEHIND.  Measured: bytes_accepted wraps 4050 -> 4 at byte
  // 4096 and the parser desynchronises at exactly that instant, even though
  // streams up to 4400 bytes were perfect.
  //
  // bytes_in is therefore a genuine depth: it grows by the number of accepted
  // bytes on each write beat and shrinks by one for every byte the reader
  // consumes.  It is FIFO_AW+1 bits wide, so a completely full FIFO (4096) is
  // representable and distinguishable from empty.
  reg  [FIFO_AW-1:0] rd_ptr_q;               // read pointer, one cycle ago
  wire               rd_advanced = (pkt_rd_ptr != rd_ptr_q);

  always @(posedge aclk) begin
    if (!aresetn)
      rd_ptr_q <= {FIFO_AW{1'b0}};
    else
      rd_ptr_q <= pkt_rd_ptr;
  end

  // (the incremental occupancy counter that used to live here was removed - it
  //  controlled nothing and its underflow caused the earlier overrun bugs; the
  //  authoritative depth is fifo_available below)

  // ----------------------------------------------------------------------
  // BRAM read (registered) + pipeline register + byte select
  // ----------------------------------------------------------------------
  // The BRAM output is registered (pkt_ram_rdata), then passed through a
  // second fabric register (pkt_ram_rdata_r) to split the timing path.
  // Without this pipeline, the path from the BRAM output tile through the
  // 8:1 mux to the FSM is too long at 200 MHz once ts_hist adds routing
  // congestion (observed WNS ~ -2.0).  The pipeline register lets the
  // placer locate pkt_ram_rdata_r adjacent to the mux/FSM, so the critical
  // path becomes: pipeline register -> 8:1 mux (1 LUT level) -> FSM
  // compare (1 LUT level) -> FSM register.
  //
  // The extra register adds one cycle of read latency.  cur_byte is
  // selected from pkt_ram_rdata_r via the *current* pkt_rd_ptr[2:0]; the
  // FSM gates consumption on byte_valid_r, a 2-cycle stability check that
  // guarantees pkt_ram_rdata_r reflects the beat the FSM is pointing at.
  //
  // Why we can't register cur_byte directly: a pipeline register on the
  // mux output captures the byte for the *pre-advance* pkt_rd_ptr (the
  // non-blocking assignment reads the old pointer), so the FSM would read
  // a stale byte in the next state -?a 1-byte off-by-one.  Keeping cur_byte
  // combinational off pkt_ram_rdata_r (which is itself a clean registered
  // copy of the BRAM output) avoids that offset while still splitting the
  // path, because pkt_ram_rdata_r is a fabric register the placer can put
  // right next to the mux.
  //
  // Throughput: 1 cycle/byte within a beat, 3 cycles at a beat boundary
  // (byte_valid_r drops for 2 cycles while pkt_ram_rdata_r crosses beats).
    // Average ~1.25 cycles/byte at 200 MHz - still ~160 MB/s, well above
    // 1 GbE line rate.
    //
    // NOTE which rate this is: 1.25 cycles/byte is the BYTE PIPELINE (how fast
    // bytes enter this FIFO). 200 MHz -> 160 MB/s, 190 MHz -> 152 MB/s, both
    // above 1 GbE's 125 MB/s.
    //
    // It is NOT the end-to-end message rate. That is 299.01 ns/message =
    // 94 MB/s = 0.75x of line rate, because per-message framing, type decode
    // and the evt_ready round trip dominate. Citing this figure as evidence of
    // message throughput would be wrong, and a report sentence did exactly that
    // before it was corrected.
  reg [63:0] pkt_ram_rdata;
  reg [63:0] pkt_ram_rdata_r;   // pipeline register: clean copy of BRAM output
  reg [FIFO_AW_BEAT-1:0] pkt_rd_ptr_prev;   // 1-cycle delayed beat
  reg [FIFO_AW_BEAT-1:0] pkt_rd_ptr_prev2;  // 2-cycle delayed beat
  always @(posedge aclk) begin
    if (!aresetn) begin
      pkt_ram_rdata     <= 64'd0;
      pkt_ram_rdata_r   <= 64'd0;
      pkt_rd_ptr_prev   <= {FIFO_AW_BEAT{1'b0}};
      pkt_rd_ptr_prev2  <= {FIFO_AW_BEAT{1'b0}};
    end else begin
      pkt_ram_rdata     <= pkt_ram[pkt_rd_ptr[FIFO_AW-1:3]];
      pkt_ram_rdata_r   <= pkt_ram_rdata;          // pipeline stage
      pkt_rd_ptr_prev   <= pkt_rd_ptr[FIFO_AW-1:3];
      pkt_rd_ptr_prev2  <= pkt_rd_ptr_prev;        // 2-cycle delay
    end
  end
  // byte_valid_r: 2-cycle stability check that pkt_ram_rdata_r reflects the
  // beat the FSM is pointing at.  Compares pkt_rd_ptr[11:3] (the beat
  // address) against pkt_rd_ptr_prev2, which holds the same beat address
  // from 2 cycles ago.  When equal, the BRAM pipeline has caught up and
  // pkt_ram_rdata_r holds the beat the FSM is pointing at.
  //
  // A single 9-bit equality would infer a CARRY4 chain whose output has
  // high fanout (18 loads) and 1.5ns routing delay at 200 MHz -?the path
  // pkt_rd_ptr -> byte_valid_r -> session_ok -> session_ok_reg/D was the
  // critical failure (WNS -0.256).  Splitting into three 3-bit slices keeps
  // each comparison in one LUT6 (6 inputs: 3 from each side), so the whole
  // check is 2 LUT levels with no CARRY4.
  //
  // Bit-mapping: pkt_rd_ptr_prev2 stores pkt_rd_ptr[11:3] in positions [8:0],
  // so prev2[i] corresponds to pkt_rd_ptr[i+3].  The three slices compare:
  //   pkt_rd_ptr[5:3]  vs prev2[2:0]  (low  3 bits of beat address)
  //   pkt_rd_ptr[8:6]  vs prev2[5:3]  (mid  3 bits)
  //   pkt_rd_ptr[11:9] vs prev2[8:6]  (high 3 bits)
  // Read-data valid: tracked by CYCLE COUNT, not by address stability.
  //
  // The BRAM read has a fixed 2-cycle latency: the address at cycle N yields
  // pkt_ram_rdata at N+1 and pkt_ram_rdata_r at N+2.  Whether
  // pkt_ram_rdata_r corresponds to pkt_rd_ptr depends only on how many cycles
  // ago that address was issued, never on whether it has changed since.
  //
  // The check used previously compared the current beat address against the
  // one from two cycles earlier.  That is equivalent ONLY while the read
  // pointer is stationary for two cycles, as it was in the single-packet
  // store-and-forward design.  Under byte-FIFO streaming the FSM advances
  // pkt_rd_ptr on consecutive cycles, so across a beat boundary the delayed
  // address never matches and the condition can never be satisfied: the FSM
  // wedges (observed parked in ST_SESSION7) with data still in the FIFO.
  //
  // The counter below is the correct formulation and is also cheaper: two
  // flops instead of three 3-bit comparators.
  reg [1:0] rd_valid_d;             // cycles since the read WORD changed
  reg [FIFO_AW-1:0] rd_word_seen;   // word most recently presented to the RAM

  // pkt_ram_rdata <= pkt_ram[rd>>3] and pkt_ram_rdata_r <= pkt_ram_rdata, so
  // the data for word rd>>3 appears in pkt_ram_rdata_r two cycles after that
  // address is presented.  The counter must therefore restart on every change
  // of the WORD address and count from there.
  //
  // It previously compared against pkt_rd_ptr_prev, which is itself registered
  // on the same edge, so on the very cycle the word changed the comparison
  // still saw the OLD value and the counter kept its saturated value 2.
  // byte_valid_r then asserted immediately and the FSM read the PREVIOUS
  // word's data -?measured: at rd=8 (word 1) it delivered 0x4E (byte 0)
  // instead of 0x00.
  wire rd_word_changed = (pkt_rd_ptr[FIFO_AW-1:3] != rd_word_seen[FIFO_AW-1:3]);

  // THREE cycles, not two.  The address for word rd>>3 is presented in the
  // cycle rd changes; pkt_ram_rdata captures it on the next edge and
  // pkt_ram_rdata_r on the one after, so the data only exists in
  // pkt_ram_rdata_r on the third cycle.  rd_word_changed is derived from a
  // registered comparison, which delays the counter start by one further
  // cycle, so 3 is what actually matches the pipeline.
  //
  // Requiring only 2 made the FSM read the PREVIOUS word at every word
  // boundary -?measured on a back-to-back stream: at rd=56 (word 7 lane 0) it
  // delivered 0x22, which is word 6 lane 6.  Only the first packet of a stream
  // survived, because every later packet crosses a word boundary mid-session.
  always @(posedge aclk) begin
    if (!aresetn) begin
      rd_valid_d   <= 2'd0;
      rd_word_seen <= {FIFO_AW{1'b0}};
    end else begin
      rd_word_seen <= pkt_rd_ptr;
      if (rd_word_changed)
        rd_valid_d <= 2'd0;          // word just changed: data is stale
      else if (rd_valid_d != 2'd3)
        rd_valid_d <= rd_valid_d + 2'd1;
    end
  end

  // Valid once the word's data has propagated to pkt_ram_rdata_r AND the
  // word has not just changed in THIS cycle.  The rd_word_changed term is
  // essential: rd_valid_d is registered, so in the very cycle pkt_rd_ptr
  // enters a new word the counter still holds the old word's saturate value
  // and byte_valid_r would be high while pkt_ram_rdata_r still holds the
  // PREVIOUS word.  Without it the FSM consumed the new word's first byte
  // with the old word's data - measured on a back-to-back stream: at rd=56
  // it delivered 0x22 (word 6 lane 0) instead of 0x30.
  wire byte_valid_r = (rd_valid_d == 2'd3) && !rd_word_changed;
  wire [7:0] cur_byte = pkt_ram_rdata_r[8*pkt_rd_ptr[2:0] +: 8];

  // Mirror of cur_byte, registered while the byte is valid.
  //
  // The sequence-gap compare in ST_SEQ_LO ({rx_seq[15:8], cur_byte} >
  // expect_seq) was the post-route critical path at -0.045 ns
  // (pkt_ram CLKARDCLK -> mux -> 16-bit compare -> gap_pending/D).  Taking the
  // byte from a flop instead of straight out of the mux breaks that path.
  // byte_valid_r is asserted for as long as the FSM needs the current byte,
  // so the registered copy is guaranteed settled before use.
  reg [7:0] cur_byte_r;
  always @(posedge aclk) begin
    if (!aresetn)
      cur_byte_r <= 8'd0;
    else if (byte_valid_r)
      cur_byte_r <= cur_byte;
  end

  // Bytes-remaining counter: tracks how many bytes are left to consume in
  // the current packet.  Loaded from pkt_wr_ptr when the packet is claimed
  // (pkt_rd_ptr starts at 0, so remaining = pkt_wr_ptr - 0 = pkt_wr_ptr).
  // Decremented by 1 in every state that advances pkt_rd_ptr.
  //
  // This replaces the naive `ptr_eq = (pkt_rd_ptr == pkt_wr_ptr)` which
  // infers a 12-bit CARRY4 equality comparator.  That CARRY4 output has 13
  // fanouts and routes across the chip (1.447ns routing delay at 200 MHz),
  // making the path from pkt_rd_ptr -> ptr_eq -> FSM -> rx_packets_CE
  // marginal (WNS -0.590).  The zero-check `pkt_bytes_rem == 0` is a NOR
  // tree (2 LUT6 levels) with the counter register placed next to the FSM,
  // eliminating the CARRY4 entirely.
  reg [FIFO_AW-1:0] pkt_bytes_rem;
  wire ptr_eq = (pkt_bytes_rem == {FIFO_AW{1'b0}});

  // Registered (one-cycle-old) copies of the two ST_EMIT conditions.
  // See the note in ST_EMIT: using the live values put a 12-bit comparison
  // into error_count's clock enable and failed timing by 4 ps.
  reg bytes_rem_gt0_r;   // bytes_rem > 0, delayed one cycle
  reg ptr_eq_r;          // pkt_bytes_rem == 0, delayed one cycle

  // ----------------------------------------------------------------------
  // Parser FSM
  // ----------------------------------------------------------------------
  reg [4:0]  state;          // current FSM state

  // ----------------------------------------------------------------------
  // Packet-done flag (single driver: this block only).
  //   Set  : when the write path sees TLAST (s_pkt_last).
  //   Clear: when the FSM claims the buffer (ST_IDLE && pkt_rx_done && enable).
  //
  // The old form was `s_pkt_last && !pkt_hold`, i.e. a TLAST arriving while
  // the FSM was still parsing the previous packet was simply DISCARDED.  In a
  // continuous DMA stream that silently loses a packet boundary; the next
  // claim then uses a stale length, the read pointer runs past the data and
  // the module wedges.  Measured on hardware: 1 and 2 packets per transfer
  // worked, 3 or more failed with bytes_rem stuck at 2040 and pkt_wr_ptr
  // wrapped (wr=290 == (1463+1457+1466) mod 4096).
  //
  // The flag is now sticky: it latches on any TLAST and is only cleared by
  // the claim.  It cannot latch a second packet while pkt_hold is asserted
  // because s_can_write keeps TREADY low then, so a beat (and hence TLAST)
  // cannot arrive during parsing.
  // ----------------------------------------------------------------------
  always @(posedge aclk) begin
    if (!aresetn)
      pkt_rx_done <= 1'b0;
    else if (s_pkt_last)
      pkt_rx_done <= 1'b1;
    else if (state == ST_IDLE && pkt_rx_done && enable)
      pkt_rx_done <= 1'b0;
  end

  // pkt_len_valid: set together with pkt_rx_done (a length was latched by
  // that TLAST) and cleared when the FSM claims the buffer.  The claim must
  // only start a parse when a length is actually pending; without this the
  // sticky pkt_rx_done let the FSM re-claim the SAME buffer repeatedly and
  // re-parse stale data (measured on hardware: a single 1463-byte packet
  // reported decode_cnt == 50 and one spurious ERROR, and every extra 8 bytes
  // appended to the transfer added another 50 spurious decodes).

  // Debug counters (surfaced in the DEBUG register): how many TLAST beats
  // arrived and how many times the FSM claimed the buffer.  These two must
  // stay equal in a healthy stream; a divergence pinpoints whether a packet
  // boundary was lost or a claim was missed.
  reg [15:0] dbg_tlast_cnt;
  reg [15:0] dbg_claim_cnt;
  // Set one cycle after ST_IDLE's guard is first satisfied, so the entry happens a cycle later than
  // the write that satisfied it.  Cleared whenever the guard is not satisfied.
  //
  // `entry_armed` is driven only by REGISTERED inputs, because `word_committed` is a 4-bit compare
  // plus an OR-reduce over `fifo_available`, and `fifo_available` is a subtractor. Putting that whole
  // chain in front of the state register's enable cost 0.163 ns and the build closed at WNS -0.069.
  // Registering the three flags first takes the subtractor and the compare off that path.
  //
  // Behaviour: the FSM now enters two cycles after the guard instead of one. That is the same
  // direction as the fix - more margin before the first read - so the benches that verify it must
  // still pass. Checked by the suite, not assumed.
  reg entry_armed;
  always @(posedge aclk) begin
    if (!aresetn) begin
      dbg_tlast_cnt <= 16'd0;
      dbg_claim_cnt <= 16'd0;
      entry_armed  <= 1'b0;
    end else begin
      if (s_pkt_last) dbg_tlast_cnt <= dbg_tlast_cnt + 16'd1;
      if (state == ST_IDLE && fifo_not_empty_live && enable)
        dbg_claim_cnt <= dbg_claim_cnt + 16'd1;
      // Stage 1: sample the guard. This is the only place the compare/subtractor is consumed.
      // One-cycle arm: the guard is satisfied this cycle, the FSM enters on the next.
      entry_armed <= (state == ST_IDLE) && fifo_not_empty_live && word_committed && enable;
    end
  end

  // last_msg_done: latched in the cycle after the final byte of a message
  // is consumed on M_AXIS.  Lets ST_MLEN_HI distinguish "packet ended
  // right after the last message (normal)" from "packet truncated mid-
  // header (error)" when pkt_rd_ptr == pkt_wr_ptr.
  reg        last_msg_done;
  reg        gap_pending;    // latched seq-gap flag (registered to break the
                             // rx_seq -> comparator -> gap_count CARRY4 path)
  reg [7:0]  session_sr [0:7];  // shift register: collects 8 session bytes
  reg [7:0]  session_mis;    // registered per-byte mismatch flags
  reg        session_ok;     // latched comparison result after 8 bytes
  reg [15:0] expect_seq;     // next expected sequence number
  reg [15:0] rx_seq;         // received sequence number
  reg [15:0] msg_len;        // current message length (from length prefix)
  reg [15:0] bytes_rem;      // bytes remaining to emit in current message
  reg [15:0] pkt_msg_cnt;    // MoldUDP64 message count for this packet
  reg [15:0] pkt_msg_rem;    // messages still to parse in this packet

  // Session comparison.
  //
  // The comparison is computed *per byte, at collection time* and stored in
  // session_mis: bit i is set when the i-th collected session byte differs
  // from SESSION slice i.  ST_SESSION_CHK then reduces the 8 registered
  // flags to one bit.
  //
  // Why not compare all 8 bytes at once in ST_SESSION_CHK: that form reads
  // the session_sr *array* fanout into 8 comparators plus an OR tree and a
  // wide select of pkt_rd_ptr-derived terms, which reproduced the critical
  // post-route path (pkt_rd_ptr_reg[1] -> msg_len logic -> session compare
  // -> session_ok/D, 5 LUT levels, 3.9 ns route, WNS -0.104 ns at 200 MHz).
  // Per-byte capture breaks that: the mismatch flag depends only on the
  // byte being collected, and CHK is an 8-input OR over flops
  // (session_mis -> LUT -> session_ok), one logic level.
  //
  // NOTE: the session shift register is also not read by the FSM, so
  // synthesis can fold it away; session_mis preserves the per-byte result.
  wire [7:0] session_mis_next = {
    (cur_byte != SESSION[7:0]),
    (cur_byte != SESSION[15:8]),
    (cur_byte != SESSION[23:16]),
    (cur_byte != SESSION[31:24]),
    (cur_byte != SESSION[39:32]),
    (cur_byte != SESSION[47:40]),
    (cur_byte != SESSION[55:48]),
    (cur_byte != SESSION[63:56])
  };
  wire       session_mismatch = |session_mis;

  // ----------------------------------------------------------------------
  // M_AXIS output register + handshake
  // ----------------------------------------------------------------------
  reg        out_valid;      // output byte is present
  reg [7:0]  out_byte;       // the byte to emit
  reg        out_last;       // TLAST: last byte of current message

  wire       out_fire  = out_valid && m_axis_tready;  // byte consumed

  assign m_axis_tvalid = out_valid;
  assign m_axis_tdata  = {56'd0, out_byte};
  assign m_axis_tkeep  = 8'h01;
  assign m_axis_tlast  = out_last;

  // ----------------------------------------------------------------------
  // Control + stats counters (enable declared earlier, before packet RAM)
  // ----------------------------------------------------------------------
  reg [63:0] rx_packets;
  reg [63:0] rx_messages;
  reg [31:0] gap_count;
  reg [31:0] gap_count_inc;  // always-registered gap_count + 1 (breaks the
                             // 32-bit CARRY4 chain from pkt_rd_ptr to
                             // gap_pending_reg/D -?the adder runs every cycle
                             // so its output is a plain register, not a live
                             // combinational path into the FSM)
  reg [31:0] error_count;

  // ----------------------------------------------------------------------
  // Soft-reset pulse (from CTRL bit1 write; self-clearing)
  // ----------------------------------------------------------------------
  // (soft_reset_r declared above; latched version of CTRL[1] write data)
  assign soft_reset_pulse = soft_reset_r;

  // Packet-complete pulse, registered.  Computing the completion condition
  // combinationally into the 64-bit rx_packets clock enable put the
  // pkt_rd_ptr_prev2 -> ptr_eq -> FSM -> CE path on the post-route critical
  // path (WNS -0.489 ns: 4 LUT levels with 4.0 ns of route to 64 CE pins).
  // Publishing it as a registered pulse ends the same logic at one flop and
  // drives the counter enable from that register.
  wire pkt_done_now =
      // Structural completion: every message announced by the MoldUDP64
      // count field has been consumed.  In the byte-FIFO design this is the
      // ONLY completion condition -?pkt_bytes_rem is a free-running byte
      // allowance, so comparing it against zero no longer marks a boundary.
      (out_fire && out_last && (pkt_msg_rem == 16'd1));
  reg pkt_done_r;

  always @(posedge aclk) begin
    if (!aresetn)
      pkt_done_r <= 1'b0;
    else if (soft_reset_pulse)
      pkt_done_r <= 1'b0;
    else
      pkt_done_r <= pkt_done_now;
  end

  // ----------------------------------------------------------------------
  // Registered ST_EMIT conditions (one cycle delayed).
  //   bytes_rem_gt0_r : bytes_rem  > 0
  //   ptr_eq_r        : pkt_bytes_rem == 0
  // Consumed by ST_EMIT instead of the live comparisons; see the note there.
  // The FSM spends multiple cycles per byte (byte_valid_r gating), so a
  // one-cycle-old copy is always evaluated by the time the next decision is
  // made, and bytes_rem only changes when the FSM advances it.
  // ----------------------------------------------------------------------
  always @(posedge aclk) begin
    if (!aresetn || soft_reset_pulse) begin
      bytes_rem_gt0_r <= 1'b0;
      ptr_eq_r        <= 1'b1;
    end else begin
      bytes_rem_gt0_r <= (bytes_rem > 16'd0);
      ptr_eq_r        <= ptr_eq;
    end
  end

  // ----------------------------------------------------------------------
  // Main FSM + output register + counters
  // ----------------------------------------------------------------------
  // Byte-consuming states gate on byte_valid_r (2-cycle stability check:
  // pkt_rd_ptr beat must match the 2-cycle-delayed beat for pkt_ram_rdata_r
  // to reflect the current pointer).  When a state advances pkt_rd_ptr,
  // byte_valid_r drops for 2 cycles at a beat boundary, so the next
  // byte-consuming state naturally waits for the pipeline register to
  // update.  The combinational cur_byte is selected from pkt_ram_rdata_r
  // (a fabric register placed near the mux) via the current pkt_rd_ptr[2:0],
  // so the critical timing path is pipeline-register -> mux -> FSM.
  always @(posedge aclk) begin
    if (!aresetn) begin
      state        <= ST_IDLE;
      pkt_rd_ptr   <= {FIFO_AW{1'b0}};
      pkt_bytes_rem <= {FIFO_AW{1'b0}};
      expect_seq   <= 16'd1;
      rx_seq       <= 16'd0;
      msg_len      <= 16'd0;
      bytes_rem    <= 16'd0;
      session_ok   <= 1'b0;
      session_mis  <= 8'd0;
      out_valid    <= 1'b0;
      out_byte     <= 8'd0;
      out_last     <= 1'b0;
      rx_packets   <= 64'd0;
      rx_messages  <= 64'd0;
      gap_count    <= 32'd0;
      gap_count_inc <= 32'd1;
      error_count  <= 32'd0;
      // soft_reset_r: single driver in the AXI write block below (which
      // also applies aresetn).  Never assign it from this FSM block.
      last_msg_done <= 1'b0;
      gap_pending  <= 1'b0;
      session_sr[0] <= 8'd0;
      session_sr[1] <= 8'd0;
      session_sr[2] <= 8'd0;
      session_sr[3] <= 8'd0;
      session_sr[4] <= 8'd0;
      session_sr[5] <= 8'd0;
      session_sr[6] <= 8'd0;
      session_sr[7] <= 8'd0;
    end else if (soft_reset_pulse) begin
      // Soft reset: clear counters and FSM, but leave pkt_ram contents
      // (they will be overwritten).
      //
      // The FIFO pointers are reset TOGETHER.  Resetting only the read
      // pointer would leave wr ahead of rd, making the occupancy arithmetic
      // report thousands of phantom bytes and desynchronise the parser -?a
      // byte FIFO has no valid state in which one pointer has moved and the
      // other has not.  The two-cycle write-commit delay registers are
      // cleared as well so they cannot lag behind the pointers.
      state        <= ST_IDLE;
      pkt_rd_ptr   <= {FIFO_AW{1'b0}};
      // The byte counters MUST be cleared with the pointers.  Leaving them set
      // while rd/wr return to 0 re-opens the read gate on stale counts, so the
      // parser reads whatever the PREVIOUS packet left in the RAM and reports
      // a session mismatch (observed: err=1 on the first packet after the TB's
      // soft reset, with only 50 of 100 bytes accepted).
      pkt_bytes_rem <= {FIFO_AW{1'b0}};
      expect_seq   <= 16'd1;
      rx_seq       <= 16'd0;
      msg_len      <= 16'd0;
      bytes_rem    <= 16'd0;
      session_ok   <= 1'b0;
      session_mis  <= 8'd0;
      out_valid    <= 1'b0;
      out_byte     <= 8'd0;
      out_last     <= 1'b0;
      rx_packets   <= 64'd0;
      rx_messages  <= 64'd0;
      gap_count    <= 32'd0;
      gap_count_inc <= 32'd1;
      error_count  <= 32'd0;
      // soft_reset_r is driven only by the AXI4-Lite write block, which
      // clears it every cycle after the write (single driver).  Do not
      // assign it here: a second driver made synthesis keep the constant
      // driver and drop the AXI one, so soft reset never pulsed.
      last_msg_done <= 1'b0;
      gap_pending  <= 1'b0;
      session_sr[0] <= 8'd0;
      session_sr[1] <= 8'd0;
      session_sr[2] <= 8'd0;
      session_sr[3] <= 8'd0;
      session_sr[4] <= 8'd0;
      session_sr[5] <= 8'd0;
      session_sr[6] <= 8'd0;
      session_sr[7] <= 8'd0;
    end else begin
      // Default: clear output register when the downstream consumes it.
      if (out_fire) begin
        out_valid <= 1'b0;
        out_last  <= 1'b0;
      end

      // ---------------------------------------------------------------
      // FSM: one byte consumed per clock tick (except ST_EMIT which
      // delegates to the output register handshake).  Byte-valid gates
      // every state that reads from the BRAM.
      // ---------------------------------------------------------------
      case (state)

        // ----- ST_IDLE: wait for a complete packet --------------------
        // pkt_rx_done is set by the write path on TLAST (one cycle after
        // the last byte lands in the RAM) and cleared by this block when
        // we claim the buffer.  During the cycle between set and clear,
        // s_can_write is held low by the pkt_rx_done term, so the next
        // packet cannot overwrite the RAM before we read byte 0.
        ST_IDLE: begin
          // Byte-FIFO: begin parsing as soon as a whole WORD is buffered.
          //
          // The session collector below reads `cur_byte` out of `pkt_ram_rdata_r`, which is a
          // snapshot of the whole 64-bit word containing `pkt_rd_ptr`.  That snapshot is taken
          // from `pkt_ram`, and the writer may not have reached the word's last lane yet - so
          // entering with one committed byte can read undefined RAM content.
          //
          // Behavioural simulation sees `X` from such a byte, `cur_byte != SESSION[0]` is
          // inconclusive, and the FSM proceeds to the next byte where real data has arrived, so
          // the RTL appeared correct for fifteen rounds.  A synthesised register holds a real
          // byte instead, the comparison is a real mismatch, and the packet is rejected - which
          // is the measured board behaviour (first packet lost, err = its byte length).
          //
          // Requiring `word_committed` HERE, and only here, fixes the first read without
          // disturbing streaming: once in ST_SESSION0 the FSM is behind bytes the writer has
          // already delivered, and every later read has a committed word.  Round 148 applied the
          // same condition continuously and deadlocked twelve suites.
          //
          // No TLAST, no per-packet hold/release - the stream delimits itself via the MoldUDP64
          // structure, so a continuous DMA burst of any length streams straight through.
          // Enter one cycle AFTER the guard is satisfied, not on the cycle it becomes true.
          //
          // `word_committed` becoming true means the word was just written, but `pkt_ram_rdata`
          // captures it on that same edge, so `pkt_ram_rdata_r` holds it two cycles later and
          // `rd_valid_d` reaches 3 one cycle after that.  Entering immediately lets the first
          // `byte_valid_r` rise on a snapshot of the previous (empty) word - measured with a zeroed
          // RAM: lane 0 read 00 against a wanted 4E, and every other lane was correct.
          //
          // The delay is at ENTRY only.  Every session, header and payload state below is untouched,
          // so a running stream sees exactly the timing it sees today - which is what rounds 148,
          // 156 and 157 all failed to preserve.
          //
          // The outer availability/guard test is gone: `entry_armed` already carries it, registered one
          // cycle earlier. Testing it again here made `word_committed` a second consumer of the same
          // 12-bit subtractor on this path - and an `always` block cannot share subexpressions across
          // two separate conditions the way a registered copy can.
          if (entry_armed) begin
            session_ok    <= 1'b1;  // assume match until a byte differs
            last_msg_done <= 1'b0;
            pkt_msg_rem   <= 16'd0;  // loaded from the count field below
            state         <= ST_SESSION0;
          end
        end

        // ----- ST_SESSION0..7: collect & compare 8 session bytes ------
        // Each state waits for byte_valid_r (pipeline latency), reads one
        // byte (cur_byte, selected from pkt_ram_rdata_r via pkt_rd_ptr[2:0]), compares it against
        // the matching slice of SESSION, stores it in the shift register,
        // advances the read pointer, and moves on.  session_ok starts at 1
        // and is cleared the first time any byte differs.
        ST_SESSION0: begin
          if (byte_valid_r && fifo_not_empty_live) begin
            session_sr[0] <= cur_byte;
            session_mis[0] <= session_mis_next[0];
            pkt_rd_ptr    <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            state         <= ST_SESSION1;
          end
        end

        ST_SESSION1: begin
          if (byte_valid_r && fifo_not_empty_live) begin
            session_sr[1] <= cur_byte;
            session_mis[1] <= session_mis_next[1];
            pkt_rd_ptr    <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            state         <= ST_SESSION2;
          end
        end

        ST_SESSION2: begin
          if (byte_valid_r && fifo_not_empty_live) begin
            session_sr[2] <= cur_byte;
            session_mis[2] <= session_mis_next[2];
            pkt_rd_ptr    <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            state         <= ST_SESSION3;
          end
        end

        ST_SESSION3: begin
          if (byte_valid_r && fifo_not_empty_live) begin
            session_sr[3] <= cur_byte;
            session_mis[3] <= session_mis_next[3];
            pkt_rd_ptr    <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            state         <= ST_SESSION4;
          end
        end

        ST_SESSION4: begin
          if (byte_valid_r && fifo_not_empty_live) begin
            session_sr[4] <= cur_byte;
            session_mis[4] <= session_mis_next[4];
            pkt_rd_ptr    <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            state         <= ST_SESSION5;
          end
        end

        ST_SESSION5: begin
          if (byte_valid_r && fifo_not_empty_live) begin
            session_sr[5] <= cur_byte;
            session_mis[5] <= session_mis_next[5];
            pkt_rd_ptr    <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            state         <= ST_SESSION6;
          end
        end

        ST_SESSION6: begin
          if (byte_valid_r && fifo_not_empty_live) begin
            session_sr[6] <= cur_byte;
            session_mis[6] <= session_mis_next[6];
            pkt_rd_ptr    <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            state         <= ST_SESSION7;
          end
        end

        ST_SESSION7: begin
          // Final session byte: store it, then evaluate the match in the
          // next state from the registered mismatch flags.
          if (byte_valid_r && fifo_not_empty_live) begin
            session_sr[7] <= cur_byte;
            session_mis[7] <= (cur_byte != SESSION[7:0]);
            pkt_rd_ptr    <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            state         <= ST_SESSION_CHK;
          end
        end

        // ----- ST_SESSION_CHK: reduce the 8 per-byte flags ------------
        // Each session byte was compared on collection (see session_mis),
        // so this state is a plain 8-input OR over flops plus the branch:
        // session_mis -> LUT6/OR -> session_ok/D and error_count CE.
        //
        // The earlier form compared all eight session_sr bytes here, which
        // put the session_sr array and pkt_rd_ptr-derived select terms on
        // the session_ok path; post-route that path was
        // pkt_rd_ptr_reg[1] -> msg_len logic -> session compare ->
        // session_ok/D (5 LUT levels, 3.9ns route, WNS -0.104 at 200 MHz).
        ST_SESSION_CHK: begin
          session_ok <= ~session_mismatch;
          if (session_mismatch) begin
            // Mismatch: count the error and resynchronise by re-entering the
            // session search.  ST_SESSION0 CONSUMES its byte and advances the
            // read pointer, so returning there makes the next buffered byte
            // the new candidate session[0] -?a sliding-window rescan with no
            // extra states.  (Returning to ST_IDLE instead, as a first
            // attempt did, left the pointer stationary and re-read the same
            // byte forever.)
            // True sliding window: rewind by 7 so the candidate start
            // advances by exactly ONE byte per retry.
            //
            // ST_SESSION0..7 consume 8 bytes and move the pointer by 8
            // before this check runs, so returning to ST_SESSION0 without
            // rewinding steps the search window by eight bytes.  The
            // resync then only ever locks onto a session header that
            // begins at a multiple of 8 relative to where the search
            // started.  Real packets begin at arbitrary offsets - packet
            // 277 of itch_loc6836.mold64 starts at 403259, i.e. mod 8 = 3
            // - so a word-granular resync slides straight past them.
            // Measured: 44 of 850 packets lost, err counting ~7600 retry
            // steps.  The rewind makes the window advance one byte.
            pkt_rd_ptr    <= pkt_rd_ptr - 7'd7;
            error_count   <= error_count + 32'd1;
            last_msg_done <= 1'b0;
            state         <= ST_SESSION0;
          end else begin
            state <= ST_SEQ_HI;
          end
        end

        // ----- ST_SEQ_HI / ST_SEQ_LO: 2-byte big-endian sequence ----
        ST_SEQ_HI: begin
          if (byte_valid_r && fifo_not_empty_live) begin
            rx_seq[15:8] <= cur_byte;
            pkt_rd_ptr   <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            state        <= ST_SEQ_LO;
          end
        end

        ST_SEQ_LO: begin
          if (byte_valid_r && fifo_not_empty_live) begin
            rx_seq[7:0] <= cur_byte;
            pkt_rd_ptr  <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            // Sequence check against the FULL assembled sequence
            // {rx_seq[15:8] (registered last cycle), cur_byte (this byte)}.
            // If the received sequence is ahead of expected, a gap occurred.
            // expect_seq advances to rx_seq_received + 1 regardless.
            //
            // The gap flag is registered here (not combinational into
            // gap_count) to break the long path: rx_seq[15:8] ->
            // 16-bit comparator -> gap_count 32-bit CARRY4.  Without this
            // register, the comparison result must reach the carry chain
            // within one 5ns cycle at 200 MHz, which is marginal (WNS
            // -0.2 to -0.5 depending on placement).  The flag is applied
            // to gap_count in the next cycle (ST_SKIP_CNT0), which is
            // still within the same packet -?gap_count is a statistics
            // counter with no downstream dependency on its timing.
            gap_pending <= ({rx_seq[15:8], cur_byte} > expect_seq);
            expect_seq <= {rx_seq[15:8], cur_byte} + 16'd1;
            gap_count_inc <= gap_count + 32'd1;  // pre-compute increment
            state      <= ST_SKIP_CNT0;
          end
        end

        // ----- ST_SKIP_CNT0 / ST_SKIP_CNT1: skip advisory count -------
        // Advances past the 2-byte count field.  No byte_valid gate (the
        // bytes were validated by byte_valid_r in ST_SEQ_LO's beat).
        // Apply the latched gap flag here (registered in ST_SEQ_LO to
        // break the rx_seq -> comparator -> gap_count CARRY4 path).
        // gap_pending is cleared in ST_SKIP_CNT1 (not ST_SKIP_CNT0) so the
        // gap_count increment (ST_SEQ_LO) and the gap_pending clear don't
        // share LUTs/CARRY4 slices in the same cycle -?this closes the last
        // timing path through the gap_count CARRY4 chain to gap_pending_reg/D.
        // gap_count_inc is purely a registered value here (no adder).
        ST_SKIP_CNT0: begin
          // First byte of the MoldUDP64 message count.  Latching it lets the
          // FSM recognise the end of the packet from (count, lengths) rather
          // than depending on TLAST, which is what makes continuous DMA
          // streams work.
          //
          // GATED on byte_valid_r: cur_byte is only meaningful once the BRAM
          // pipeline has caught up with pkt_rd_ptr.  These states used to run
          // ungated because the count was purely advisory; now the count
          // DETERMINES the packet length, so sampling a stale cur_byte at a
          // beat boundary corrupts it and the structural end-of-packet fires
          // early (on hardware packet 1 stopped with 585 of 1463 bytes left).
          if (byte_valid_r && fifo_not_empty_live) begin
            pkt_msg_cnt[15:8] <= cur_byte;
            pkt_rd_ptr    <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            // gap_count_inc was pre-computed in ST_SEQ_LO (registered).
            // No CARRY4 chain here, which breaks the false path from
            // pkt_rd_ptr through the gap_count adder to gap_pending_reg/D.
            if (gap_pending)
              gap_count <= gap_count_inc;  // mux only (no adder)
            state       <= ST_SKIP_CNT1;
          end
        end

        ST_SKIP_CNT1: begin
          if (byte_valid_r && fifo_not_empty_live) begin
            pkt_msg_cnt[7:0] <= cur_byte;
            // Packet message count is now known: {MSB latched last cycle,
            // this byte}.  Track messages remaining so the end of the packet
            // is determined structurally instead of by TLAST.
            pkt_msg_rem   <= {pkt_msg_cnt[15:8], cur_byte};
            pkt_rd_ptr    <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            gap_pending   <= 1'b0;
            state         <= ST_MLEN_HI;
          end
        end

        // ----- ST_MLEN_HI / ST_MLEN_LO: 2-byte message length ---------
        ST_MLEN_HI: begin
          if (byte_valid_r && fifo_not_empty_live) begin
            // Genuinely no data left: the committed FIFO is empty.
            //
            // This must NOT be the ptr_eq test (pkt_bytes_rem == 0).
            // pkt_bytes_rem is a free-running byte allowance that is
            // decremented per consumed byte and never reloaded per
            // packet, so as a 12-bit counter it returns to zero exactly
            // every 4096 bytes - abandoning the current packet at
            // whatever message boundary falls there.  On the real
            // capture that lost packets every 4096 bytes (the first at
            // stream offset 4096*98 = 401408, inside packet 275).
            // A truly empty FIFO is what 'no more bytes available'
            // means here.
            if (!fifo_not_empty) begin
              if (!last_msg_done) begin
                error_count <= error_count + 32'd1;
              end
              last_msg_done <= 1'b0;
              // rx_packets is incremented by the registered pkt_done_r pulse.
              state         <= ST_IDLE;
            end else begin
              msg_len[15:8] <= cur_byte;
              pkt_rd_ptr    <= pkt_rd_ptr + 7'd1;
              pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
              state         <= ST_MLEN_LO;
            end
          end
        end

        ST_MLEN_LO: begin
          if (byte_valid_r && fifo_not_empty_live) begin
            msg_len[7:0] <= cur_byte;
            pkt_rd_ptr   <= pkt_rd_ptr + 7'd1;
            pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
            // bytes_rem = full message length = {high_byte (registered last
            // cycle in ST_MLEN_HI), low_byte (cur_byte this cycle)}.
            bytes_rem    <= {msg_len[15:8], cur_byte};
            state        <= ST_EMIT_LEN_HI;
          end
        end

        // ----- ST_EMIT_LEN_HI / ST_EMIT_LEN_LO: emit 2-byte length prefix
        // prefix bytes go out with out_last=0 (TLAST belongs to the final
        // body byte, not the prefix).
        ST_EMIT_LEN_HI: begin
          if (!out_valid) begin
            out_valid <= 1'b1;
            out_byte  <= msg_len[15:8];
            out_last  <= 1'b0;
            state     <= ST_EMIT_LEN_LO;
          end
        end

        ST_EMIT_LEN_LO: begin
          if (!out_valid) begin
            out_valid <= 1'b1;
            out_byte  <= msg_len[7:0];
            out_last  <= 1'b0;
            state     <= ST_EMIT;
          end
        end

        // ----- ST_EMIT: message body ---------------------------------
        // The output register presents one byte per beat and waits for
        // M_AXIS TREADY.  When it is free and bytes remain, load the next
        // byte.  When the last byte is consumed, loop back to ST_MLEN_HI
        // for the next message in this packet.
        ST_EMIT: begin
          if (!out_valid) begin
            // Output register is free: load the next byte if one remains.
            //
            // Uses the REGISTERED one-cycle-old comparisons
            // (bytes_rem_gt0_r / ptr_eq_r), not the live values.  Driving
            // error_count's clock enable from `bytes_rem > 0` + `ptr_eq`
            // put bytes_rem[4] through a LUT5/LUT6 cone into
            // error_count_reg[*]/CE: 4 logic levels plus 3.6 ns of route,
            // WNS -0.004 ns even after the write-adder rework.  Both
            // conditions are only consulted once bytes_rem has settled, so
            // evaluating them one cycle early removes the path.
            if (bytes_rem_gt0_r) begin
              // Underflow guard: emit only while the FIFO really holds the
              // byte.  In the byte-FIFO design there is no per-packet byte
              // allowance, so the old ptr_eq test (pkt_bytes_rem == 0) no
              // longer marks a buffer boundary and would read stale RAM.
              if (!fifo_not_empty_live) begin
                // The FIFO being momentarily empty does NOT mean the packet is
                // truncated. bytes_committed advances only on a full 64-bit
                // word (or on tail_publish after TLAST), so early in a packet -
                // and always at the head of a stream - the reader can arrive
                // before the first word is committed.
                //
                // Measured on hardware before this fix: the first packet of
                // every stream was consumed as errors, one per byte, giving
                // error_count == packet length, and the loss grew as the input
                // was delivered more slowly (whole buffer: 1 packet lost;
                // 64-byte chunks: 2 of 3 packets lost).
                //
                // Two conditions mean "bytes of this packet are still on
                // their way to the RAM", and in both the reader must wait
                // rather than declare truncation:
                //
                //   tail_pending : TLAST seen, tail word not yet published
                //   cm_valid     : a registered commit is in flight
                //
                // Measured on hardware without this: the first packet of every
                // stream was consumed as errors, one per byte, so error_count
                // equalled the packet length; 849 of 850 packets, 43379 of
                // 43428 messages, gap=1.
                //
                // A third term, (pkt_wr_ptr != pkt_rd_ptr), was tried as well -
                // reasoning that bytes accepted but not yet committed should
                // also hold the reader. It REGRESSED: 849 packets and err=1463
                // on 12 consecutive runs, where this version measured 850 and
                // 43428. It is deliberately absent.
                if (tail_pending || cm_valid) begin
                  // Data is still arriving: hold here and emit nothing.
                  pkt_rd_ptr    <= pkt_rd_ptr;
                  pkt_bytes_rem <= pkt_bytes_rem;
                end else begin
                  // The packet really has ended with bytes still owed:
                  // truncated / malformed.
                  error_count   <= error_count + 32'd1;
                  last_msg_done <= 1'b0;
                  // rx_packets is incremented by the registered pkt_done_r pulse.
                  state         <= ST_IDLE;
                end
              end else if (byte_valid_r) begin
                out_valid <= 1'b1;
                out_byte  <= cur_byte;
                out_last  <= (bytes_rem == 16'd1);
                bytes_rem <= bytes_rem - 16'd1;
                pkt_rd_ptr    <= pkt_rd_ptr + 7'd1;
                pkt_bytes_rem <= pkt_bytes_rem - 7'd1;
              end
            end else begin
              // msg_len == 0 means zero-length message; treat as done and
              // move to the next message length header.
              state <= ST_MLEN_HI;
            end
          end
          // When out_valid==1 the FSM stalls until out_fire clears it.
        end

        default: begin
          state <= ST_IDLE;
        end
      endcase

      // When the last byte of a message is consumed on M_AXIS, advance
      // the message counter and loop back to read the next message length.
      // This fires one cycle after out_last was set (when out_fire clears
      // out_valid with out_last==1).  Latch last_msg_done so ST_MLEN_HI can
      // tell a clean end-of-packet from a truncation.
      if (out_fire && out_last) begin
        rx_messages   <= rx_messages + 64'd1;
        last_msg_done <= 1'b1;
        // Count down the messages that remain in this packet.  When the last
        // one is done the packet is complete by construction, so release the
        // buffer without waiting for (or relying on) TLAST.
        if (pkt_msg_rem != 16'd0)
          pkt_msg_rem <= pkt_msg_rem - 16'd1;
        // Transition to next message unless the packet is exhausted.
        if (state == ST_EMIT) begin
          state <= ST_MLEN_HI;
        end
      end

      // Structural end of packet: every message announced by the MoldUDP64
      // count field has been consumed.  Release the buffer and resynchronise
      // at the next packet header.  This is what makes the module work on a
      // continuous DMA stream, where TLAST-driven release is too coarse.
      if (out_fire && out_last && (pkt_msg_rem == 16'd1)) begin
        last_msg_done <= 1'b0;
        state         <= ST_IDLE;
      end

      // When the packet is fully consumed (parser reaches end between
      // messages), release the buffer.  The packet count comes from the
      // registered pkt_done_r pulse (third term of pkt_done_now).
      // This is detected in ST_MLEN_HI when pkt_rd_ptr == pkt_wr_ptr
      // (handled inline above) and also here as a safety net.
      // Count completed packets off the registered pulse.  One cycle later
      // than the FSM event, which is irrelevant for a statistic and keeps
      // the long completion logic out of this counter's clock enable.
      if (pkt_done_r)
        rx_packets <= rx_packets + 64'd1;
    end
  end

  // ----------------------------------------------------------------------
  // AXI4-Lite stats + control
  // ----------------------------------------------------------------------
  reg        b_valid;
  reg        r_valid;
  reg [31:0] r_data;

  // ---- write channel --------------------------------------------------
  // Accept AW/W when both valid and no B beat pending.  CTRL (offset 0x18,
  // word index 6) is the only RW register; all others are RO and writes are
  // silently discarded.  CTRL bit1 is soft_reset (self-clearing pulse).
  wire wr_fire = s_axi_awvalid && s_axi_wvalid && !b_valid;

  assign s_axi_awready = wr_fire;
  assign s_axi_wready  = wr_fire;

  always @(posedge aclk) begin
    if (!aresetn) begin
      b_valid      <= 1'b0;
      enable       <= 1'b0;
      soft_reset_r <= 1'b0;
    end else begin
      // One-cycle soft-reset pulse: default 0, set by the CTRL write.
      soft_reset_r <= 1'b0;
      if (wr_fire) begin
        b_valid <= 1'b1;
        if (s_axi_awaddr[4:2] == 3'd6 && s_axi_wstrb[0]) begin
          enable       <= s_axi_wdata[0];
          soft_reset_r <= s_axi_wdata[1];
        end
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
          3'd0: r_data <= rx_packets[31:0];    // RX_PACKETS_LO  (0x00)
          3'd1: r_data <= rx_packets[63:32];   // RX_PACKETS_HI  (0x04)
          3'd2: r_data <= rx_messages[31:0];   // RX_MESSAGES_LO (0x08)
          3'd3: r_data <= rx_messages[63:32];  // RX_MESSAGES_HI (0x0C)
          3'd4: r_data <= gap_count;           // GAP_COUNT      (0x10)
          3'd5: r_data <= error_count;         // ERROR_COUNT    (0x14)
          3'd6: r_data <= {30'd0, soft_reset_r, enable}; // CTRL (0x18)
          // DEBUG (0x1C, read-only): live FSM/pointer observability.  Added
          // while xsim could not reproduce a hardware-only stall (the TB
          // drives M_AXIS with no backpressure from a real book), so the
          // live state has to be readable over AXI4-Lite instead.
          //   [4:0]  state
          //   [5]    pkt_rx_done
          //   [6]    pkt_hold
          //   [7]    pkt_rx_active
          //   [8]    byte_valid_r
          //   [20:9]  pkt_wr_ptr   (bytes written so far, 12 bits)
          //   [31:21] pkt_bytes_rem (bytes left in packet, low 11 bits)
          //
          // The whole word MUST fit in 32 bits: an earlier layout concatenated
          // to 48 bits (13-bit bytes_rem placed before a 12-bit wr_ptr), so
          // the upper bits -?including all of pkt_wr_ptr -?were dropped on
          // read-back and the register appeared to read "0" always.
          3'd7: r_data <= {pkt_bytes_rem[10:0], pkt_wr_ptr,
                           byte_valid_r, pkt_rx_active, fifo_not_empty,
                           pkt_rx_done, state};
          default: r_data <= 32'd0;
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




