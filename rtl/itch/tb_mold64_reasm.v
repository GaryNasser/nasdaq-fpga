// ============================================================================
// SUPERSEDED - THIS TESTBENCH HANGS. DO NOT USE IT AS A VERIFICATION GATE.
//
// Written for the pre-byte-FIFO store-and-forward design. After mold64_reasm was
// rewritten as a true byte FIFO this testbench waits on handshakes the current
// module no longer satisfies, so it runs forever instead of printing TB-ALL-PASS.
//
// The live verification suite is in tools/ - see docs/final-report.md 9.1.
// Kept only as a historical record of the original buffer's behaviour.
// ============================================================================
// tb_mold64_reasm: self-checking testbench for mold64_reasm.
//
// Checks (all print [PASS]/[FAIL], end on TB-ALL-PASS):
//   1. after reset all stat registers read 0, CTRL reads 0
//   2. enable + 1 packet / 1 message -> M_AXIS emits len-prefix + body,
//      TLAST on last byte; RX_PACKETS=1, RX_MESSAGES=1, GAP=0, ERR=0
//   3. multi-message packet (count=2) -> RX_MESSAGES cumulative
//   4. sequence gap (rx_seq > expect_seq) -> GAP_COUNT++
//   5. session mismatch -> ERROR_COUNT++, packet dropped, no M_AXIS output
//   6. M_AXIS backpressure: out_valid holds, no bytes lost, drain intact
//   7. soft reset: counters -> 0, FSM idle, enable untouched
//   8. 3 packets sequential -> RX_PACKETS=3, RX_MESSAGES=3, GAP=0, ERR=0
//   9. final stat check
//
// Conventions match tb_loopback_dma.v: timescale 1ns/1ps, 200 MHz clock
// (#2.5), task check, task axi_read, task s_send / m_recv, fork/join with
// separate loop variables, errors counter, TB-ALL-PASS / TB-FAILED.

`timescale 1ns / 1ps

module tb_mold64_reasm;

  // Clock / reset
  reg         aclk = 0;
  reg         aresetn = 0;
  always #2.5 aclk = ~aclk;   // 200 MHz functional test clock

  // AXI4-Lite
  reg  [4:0]  s_axi_awaddr = 0;
  reg  [2:0]  s_axi_awprot = 0;
  reg         s_axi_awvalid = 0;
  wire        s_axi_awready;
  reg  [31:0] s_axi_wdata = 0;
  reg  [3:0]  s_axi_wstrb = 4'b1111;
  reg         s_axi_wvalid = 0;
  wire        s_axi_wready;
  wire [1:0]  s_axi_bresp;
  wire        s_axi_bvalid;
  reg         s_axi_bready = 1;
  reg  [4:0]  s_axi_araddr = 0;
  reg  [2:0]  s_axi_arprot = 0;
  reg         s_axi_arvalid = 0;
  wire        s_axi_arready;
  wire [31:0] s_axi_rdata;
  wire [1:0]  s_axi_rresp;
  wire        s_axi_rvalid;
  reg         s_axi_rready = 1;

  // AXI-Stream slave side (TB drives, DUT receives)
  reg  [63:0] s_axis_tdata = 0;
  reg  [7:0]  s_axis_tkeep = 8'hFF;
  reg         s_axis_tvalid = 0;
  wire        s_axis_tready;
  reg         s_axis_tlast = 0;

  // AXI-Stream master side (DUT drives, TB receives)
  wire [7:0]  m_axis_tdata;
  wire [7:0]  m_axis_tkeep;
  wire        m_axis_tvalid;
  reg         m_axis_tready = 1;
  wire        m_axis_tlast;

  mold64_reasm #(
    .SESSION (64'h4E41534441513031),  // "NASDAQ01"
    .FIFO_AW(12)
  ) dut (
    .aclk(aclk), .aresetn(aresetn),
    .s_axi_awaddr(s_axi_awaddr), .s_axi_awprot(s_axi_awprot),
    .s_axi_awvalid(s_axi_awvalid), .s_axi_awready(s_axi_awready),
    .s_axi_wdata(s_axi_wdata), .s_axi_wstrb(s_axi_wstrb),
    .s_axi_wvalid(s_axi_wvalid), .s_axi_wready(s_axi_wready),
    .s_axi_bresp(s_axi_bresp), .s_axi_bvalid(s_axi_bvalid), .s_axi_bready(s_axi_bready),
    .s_axi_araddr(s_axi_araddr), .s_axi_arprot(s_axi_arprot),
    .s_axi_arvalid(s_axi_arvalid), .s_axi_arready(s_axi_arready),
    .s_axi_rdata(s_axi_rdata), .s_axi_rresp(s_axi_rresp),
    .s_axi_rvalid(s_axi_rvalid), .s_axi_rready(s_axi_rready),

    .s_axis_tdata(s_axis_tdata), .s_axis_tkeep(s_axis_tkeep),
    .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .s_axis_tlast(s_axis_tlast),

    .m_axis_tdata(m_axis_tdata), .m_axis_tkeep(m_axis_tkeep),
    .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready),
    .m_axis_tlast(m_axis_tlast)
  );

  // ----------------------------------------------------------------------
  integer errors = 0;

  task check(input cond, input [511:0] name);
    begin
      if (cond) $display("[PASS] %0s", name);
      else begin $display("[FAIL] %0s", name); errors = errors + 1; end
    end
  endtask

  // AXI4-Lite write (AW+W simultaneously, wait for B).
  task axi_write(input [4:0] addr, input [31:0] data);
    begin : wr_blk
      reg        wr_done;
      reg        b_done;
      wr_done = 0;
      b_done  = 0;
      @(negedge aclk);
      s_axi_awaddr  <= addr;
      s_axi_awvalid <= 1;
      s_axi_wdata   <= data;
      s_axi_wstrb   <= 4'b1111;
      s_axi_wvalid  <= 1;
      while (!wr_done) begin
        @(posedge aclk);
        if (s_axi_awvalid && s_axi_awready && s_axi_wvalid && s_axi_wready) begin
          wr_done       = 1;
          s_axi_awvalid <= 0;
          s_axi_wvalid  <= 0;
        end
      end
      while (!b_done) begin
        @(posedge aclk);
        if (s_axi_bvalid && s_axi_bready) b_done = 1;
      end
      @(negedge aclk);
    end
  endtask

  // The packet counter is updated from a registered completion pulse (an
  // RTL change that keeps the long FSM/pointer compare out of the counter's
  // clock enable; see mold64_reasm).  Allow a few cycles for the pulse and
  // the registered AXI read address to land before sampling statistics.
  task settle_stats;
    begin
      repeat (8) @(posedge aclk);
    end
  endtask

  // AXI4-Lite read (RREADY tied high).
  task axi_read(input [4:0] addr, output [31:0] data);
    begin
      @(negedge aclk);
      s_axi_araddr  <= addr;
      s_axi_arvalid <= 1;
      @(negedge aclk);
      while (!s_axi_rvalid) @(negedge aclk);
      data = s_axi_rdata;
      s_axi_arvalid <= 0;
      @(negedge aclk);
    end
  endtask

  // Drive one S_AXIS beat and wait for the handshake at posedge.
  task s_send(input [63:0] d, input [7:0] tk, input last);
    begin : hs
      reg done;
      done = 0;
      @(negedge aclk);
      s_axis_tdata  <= d;
      s_axis_tkeep  <= tk;
      s_axis_tvalid <= 1;
      s_axis_tlast  <= last;
      while (!done) begin
        @(posedge aclk);
        if (s_axis_tvalid && s_axis_tready) begin
          done          = 1;
          s_axis_tvalid <= 0;
          s_axis_tlast  <= 0;
        end
      end
      @(negedge aclk);
    end
  endtask

  // Read one M_AXIS beat (blocking until TVALID).  Returns byte / last.
  task m_recv(output [7:0] d, output last);
    begin
      @(negedge aclk);
      while (!m_axis_tvalid) @(negedge aclk);
      d   = m_axis_tdata;
      last = m_axis_tlast;
      @(negedge aclk);
    end
  endtask

  // Receive one message of n beats, comparing each beat against an expected
  // byte computed by a caller-provided function of the beat index.  To stay
  // within Verilog-2001 (no function calls in loop bodies for some tools and
  // no array task ports), the caller sets module-level helper regs before
  // calling this task:
  //   exp_type  : expected byte at body offset 0
  //   exp_base  : base OR-mask for body offset >= 1
  //   exp_lenlo : expected low byte of the length prefix (beat 1)
  // The task checks TLAST on the last beat and clear elsewhere.
  reg [7:0] exp_type;
  reg [7:0] exp_base;
  reg [7:0] exp_lenlo;
  // When 1, recv_check expects beat 0 = exp_lenlo (the leading 0x00 length
  // byte was already consumed by the caller, e.g. after backpressure).
  reg        skip_lead_zero = 0;

  task recv_check(input integer n);
    begin : rc
      integer k;
      reg [7:0] rb;
      reg        rl;
      reg [7:0] e;
      for (k = 0; k < n; k = k + 1) begin : beat
        reg [7:0] idx;
        m_recv(rb, rl);
        if (!skip_lead_zero) begin
          if (k == 0)      e = 8'h00;
          else if (k == 1) e = exp_lenlo;
          else begin
            idx = k[7:0] - 8'd2;
            e = (idx == 0) ? exp_type : (exp_base | idx);
          end
        end else begin
          // Leading 0x00 already consumed: beat 0 is exp_lenlo, beat 1 is
          // exp_type, beat k>=2 is exp_base | (k-1).
          if (k == 0) e = exp_lenlo;
          else begin
            idx = k[7:0] - 8'd1;
            e = (idx == 0) ? exp_type : (exp_base | idx);
          end
        end
        if (rb !== e) begin
          $display("  beat %0d: expected %02h got %02h", k, e, rb);
          errors = errors + 1;
        end
        if (k == n - 1) begin
          if (rl !== 1'b1) begin
            $display("  TLAST expected on last beat of msg (n=%0d)", n);
            errors = errors + 1;
          end
        end else begin
          if (rl !== 1'b0) begin
            $display("  unexpected TLAST on beat %0d/%0d", k, n);
            errors = errors + 1;
          end
        end
      end
    end
  endtask

  // ----------------------------------------------------------------------
  // Shared byte buffer + helpers for building / sending MoldUDP64 packets.
  // Verilog-2001 tasks cannot take array ports, so pack_and_send() reads
  // its arguments from module-level regs set by the caller:
  //   nmsgs      : number of messages (1..3)
  //   seq        : 16-bit sequence number (BE on the wire)
  //   m0l,m1l,m2l: body byte counts for messages 0,1,2
  //   body0,body1,body2 : message body bytes
  // ----------------------------------------------------------------------
  reg [7:0] bytes [0:1023];

  integer nmsgs;
  integer m0l, m1l, m2l;
  reg [15:0] seq;
  reg [7:0]  body0 [0:255];
  reg [7:0]  body1 [0:255];
  reg [7:0]  body2 [0:255];

  task pack_and_send;
    begin : ps
      integer total, p, rem, nfill, bi;
      reg [7:0] b0,b1,b2,b3,b4,b5,b6,b7;

      total = 8 + 2 + 2 + 2 + m0l;   // session + seq + count + msg0_len + body0
      if (nmsgs > 1) total = total + 2 + m1l;
      if (nmsgs > 2) total = total + 2 + m2l;

      p = 0;
      // session "NASDAQ01"
      bytes[p]=8'h4E;p=p+1; bytes[p]=8'h41;p=p+1; bytes[p]=8'h53;p=p+1;
      bytes[p]=8'h44;p=p+1; bytes[p]=8'h41;p=p+1; bytes[p]=8'h51;p=p+1;
      bytes[p]=8'h30;p=p+1; bytes[p]=8'h31;p=p+1;
      // seq (BE)
      bytes[p]=seq[15:8];p=p+1; bytes[p]=seq[7:0];p=p+1;
      // count (BE) = nmsgs
      bytes[p]=8'h00;p=p+1; bytes[p]=nmsgs[7:0];p=p+1;
      // message 0: len + body
      bytes[p]=m0l[15:8];p=p+1; bytes[p]=m0l[7:0];p=p+1;
      for (bi = 0; bi < m0l; bi = bi+1) begin bytes[p]=body0[bi];p=p+1; end
      // message 1
      if (nmsgs > 1) begin
        bytes[p]=m1l[15:8];p=p+1; bytes[p]=m1l[7:0];p=p+1;
        for (bi = 0; bi < m1l; bi = bi+1) begin bytes[p]=body1[bi];p=p+1; end
      end
      // message 2
      if (nmsgs > 2) begin
        bytes[p]=m2l[15:8];p=p+1; bytes[p]=m2l[7:0];p=p+1;
        for (bi = 0; bi < m2l; bi = bi+1) begin bytes[p]=body2[bi];p=p+1; end
      end

      // Drive beats.
      rem = total;
      p   = 0;
      while (rem > 0) begin
        nfill = (rem >= 8) ? 8 : rem;
        b0=bytes[p+0];
        b1=(nfill>1)?bytes[p+1]:8'h00;
        b2=(nfill>2)?bytes[p+2]:8'h00;
        b3=(nfill>3)?bytes[p+3]:8'h00;
        b4=(nfill>4)?bytes[p+4]:8'h00;
        b5=(nfill>5)?bytes[p+5]:8'h00;
        b6=(nfill>6)?bytes[p+6]:8'h00;
        b7=(nfill>7)?bytes[p+7]:8'h00;
        // AXI-Stream first byte in lowest lane: b0 -> tdata[7:0].
        s_send({b7,b6,b5,b4,b3,b2,b1,b0},
               (nfill==8)?8'hFF:(nfill==7)?8'h7F:(nfill==6)?8'h3F:
               (nfill==5)?8'h1F:(nfill==4)?8'h0F:(nfill==3)?8'h07:
               (nfill==2)?8'h03:8'h01,
               (nfill==rem)?1'b1:1'b0);
        p   = p + nfill;
        rem = rem - nfill;
      end
    end
  endtask

  reg [31:0] v0, v1, v2, v3, v4, v5, v6;
  integer i, j, k;
  // Scratch regs/integers for building non-standard (session-mismatch)
  // packets inline (xvlog rejects local declarations in named blocks).
  reg [7:0] bb0,bb1,bb2,bb3,bb4,bb5,bb6,bb7;
  integer bx_total, bx_p, bx_rem, bx_nfill, bx_idle;

  initial begin
    // ----- reset -----
    repeat (4) @(negedge aclk);
    aresetn = 1;
    repeat (2) @(negedge aclk);

    // ====================================================================
    // 1. reset values
    // ====================================================================
    axi_read(5'h00, v0); check(v0 == 32'd0, "rset RX_PACKETS_LO");
    axi_read(5'h04, v0); check(v0 == 32'd0, "rset RX_PACKETS_HI");
    axi_read(5'h08, v0); check(v0 == 32'd0, "rset RX_MESSAGES_LO");
    axi_read(5'h0C, v0); check(v0 == 32'd0, "rset RX_MESSAGES_HI");
    axi_read(5'h10, v0); check(v0 == 32'd0, "rset GAP_COUNT");
    axi_read(5'h14, v0); check(v0 == 32'd0, "rset ERROR_COUNT");
    axi_read(5'h18, v0); check(v0 == 32'd0, "rset CTRL");

    // ====================================================================
    // 2. enable + single packet, single message
    // ====================================================================
    axi_write(5'h18, 32'h1);   // CTRL.bit0=1 (enable)

    nmsgs = 1;
    seq   = 16'd1;
    m0l   = 36;
    for (i = 0; i < 36; i = i + 1)
      body0[i] = (i == 0) ? 8'h41 : 8'h00 | i[7:0];
    exp_type  = 8'h41;
    exp_base  = 8'h00;
    exp_lenlo = 8'h24;

    fork
      begin : t2_prod
        pack_and_send;
      end
      begin : t2_cons
        recv_check(38);
      end
    join

    settle_stats;
    axi_read(5'h00, v0); check(v0 == 32'd1, "t2 RX_PACKETS_LO==1");
    axi_read(5'h08, v0); check(v0 == 32'd1, "t2 RX_MESSAGES_LO==1");
    axi_read(5'h10, v0); check(v0 == 32'd0, "t2 GAP_COUNT==0");
    axi_read(5'h14, v0); check(v0 == 32'd0, "t2 ERROR_COUNT==0");

    // ====================================================================
    // 2b. tkeep popcount / pkt_wr_ptr byte accounting
    // ====================================================================
    // Regression for the packet write-pointer width bug that only showed up
    // on hardware: `4'd1 + s_axis_tkeep[1] + ... + s_axis_tkeep[7]` was
    // evaluated in 1 bit because every tkeep bit is 1 bit wide, so the
    // popcount wrapped modulo 2 and pkt_wr_ptr advanced by ~half the bytes.
    // A 1463-byte packet ended at pkt_wr_ptr=731 and the FSM then read past
    // the end of the packet on the board.
    //
    // Feed exactly one packet of known size and confirm the DEBUG register
    // reports the full byte count.  The packet is 8 session + 2 seq +
    // 2 count + (2 + 36) = 50 bytes.

    // Sample pkt_wr_ptr while the packet is still owned by the FSM.  Doing
    // this after recv_check would read 0, because the FSM clears the pointer
    // once it releases the buffer.  So: store the packet with the downstream
    // stalled (TREADY low), read the pointer, then release and drain.
    axi_write(5'h18, 32'h3);   // soft reset
    repeat (4) @(negedge aclk);
    axi_write(5'h18, 32'h1);   // enable
    nmsgs = 1;
    seq   = 16'd1;
    m0l   = 36;
    for (i = 0; i < 36; i = i + 1)
      body0[i] = (i == 0) ? 8'h41 : 8'h00 | i[7:0];

    m_axis_tready <= 0;
    @(negedge aclk);
    @(negedge aclk);               // ensure TREADY is REALLY low before sending
    pack_and_send;                 // all 50 bytes now accepted into the FIFO
    repeat (8) @(negedge aclk);    // let the last beat settle
    axi_read(5'h1C, v0);           // word 7 = DEBUG
    $display("  t2b DEBUG=0x%08x pkt_wr_ptr=%0d", v0, (v0 >> 9) & 12'hFFF);
    // t2b is preceded by a soft reset, which now clears the FIFO byte counters
    // along with the pointers, so exactly one 50-byte packet is in flight here.
    // pkt_wr_ptr is byte granular, so it must equal the raw byte count — a
    // stronger invariant than the word-aligned approximation that was needed
    // while the pointer advanced once per committed word.
    check(((v0 >> 9) & 12'hFFF) == 12'd50,
          "t2b pkt_wr_ptr counts all 50 packet bytes");

    // Release backpressure and drain the message so later tests start clean.
    m_axis_tready <= 1;
    repeat (4) @(negedge aclk);
    exp_type  = 8'h41;
    exp_base  = 8'h00;
    exp_lenlo = 8'h24;
    recv_check(38);
    settle_stats;
    axi_read(5'h14, v0); check(v0 == 32'd0, "t2b ERROR_COUNT==0");

    // ====================================================================
    // 3. multi-message packet (count=2)
    // ====================================================================
    nmsgs = 2;
    seq   = 16'd2;
    m0l   = 36;
    for (i = 0; i < 36; i = i + 1)
      body0[i] = (i == 0) ? 8'h41 : 8'hA0 | i[7:0];
    m1l   = 31;
    for (i = 0; i < 31; i = i + 1)
      body1[i] = (i == 0) ? 8'h45 : 8'hB0 | i[7:0];

    fork
      begin : t3_prod
        pack_and_send;
      end
      begin : t3_cons
        exp_type = 8'h41; exp_base = 8'hA0; exp_lenlo = 8'h24;
        recv_check(38);
        exp_type = 8'h45; exp_base = 8'hB0; exp_lenlo = 8'h1F;
        recv_check(33);
      end
    join

    settle_stats;
    axi_read(5'h00, v0); check(v0 == 32'd2, "t3 RX_PACKETS_LO==2");
    axi_read(5'h08, v0); check(v0 == 32'd3, "t3 RX_MESSAGES_LO==3 (cum)");
    axi_read(5'h10, v0); check(v0 == 32'd0, "t3 GAP_COUNT==0");
    axi_read(5'h14, v0); check(v0 == 32'd0, "t3 ERROR_COUNT==0");

    // ====================================================================
    // 4. sequence gap
    // ====================================================================
    // Packet A: seq=5 (expect_seq is 3) -> gap.
    nmsgs = 1;  seq = 16'd5;  m0l = 36;
    for (i = 0; i < 36; i = i + 1)
      body0[i] = (i == 0) ? 8'h47 : 8'hC0 | i[7:0];
    exp_type = 8'h47; exp_base = 8'hC0; exp_lenlo = 8'h24;
    fork
      begin : t4_pa
        pack_and_send;
      end
      begin : t4_ca
        recv_check(38);
      end
    join
    // Packet B: seq=3 (behind) -> no new gap.
    nmsgs = 1;  seq = 16'd3;  m0l = 36;
    for (i = 0; i < 36; i = i + 1)
      body0[i] = (i == 0) ? 8'h53 : 8'hD0 | i[7:0];
    exp_type = 8'h53; exp_base = 8'hD0; exp_lenlo = 8'h24;
    fork
      begin : t4_pb
        pack_and_send;
      end
      begin : t4_cb
        recv_check(38);
      end
    join

    axi_read(5'h10, v0); check(v0 == 32'd1, "t4 GAP_COUNT==1");
    settle_stats;
    axi_read(5'h00, v0); check(v0 == 32'd4, "t4 RX_PACKETS_LO==4 (cum)");
    axi_read(5'h08, v0); check(v0 == 32'd5, "t4 RX_MESSAGES_LO==5 (cum)");
    axi_read(5'h14, v0); check(v0 == 32'd0, "t4 ERROR_COUNT==0");

    // ====================================================================
    // 5. session mismatch
    // ====================================================================
    bx_total = 8 + 2 + 2 + 2 + 36;
    bx_p = 0;
    bytes[bx_p]=8'h57;bx_p=bx_p+1; bytes[bx_p]=8'h52;bx_p=bx_p+1;
    bytes[bx_p]=8'h4F;bx_p=bx_p+1; bytes[bx_p]=8'h4E;bx_p=bx_p+1;
    bytes[bx_p]=8'h47;bx_p=bx_p+1; bytes[bx_p]=8'h30;bx_p=bx_p+1;
    bytes[bx_p]=8'h30;bx_p=bx_p+1; bytes[bx_p]=8'h30;bx_p=bx_p+1;
    bytes[bx_p]=8'h00;bx_p=bx_p+1; bytes[bx_p]=8'h06;bx_p=bx_p+1;
    bytes[bx_p]=8'h00;bx_p=bx_p+1; bytes[bx_p]=8'h01;bx_p=bx_p+1;
    bytes[bx_p]=8'h00;bx_p=bx_p+1; bytes[bx_p]=8'h24;bx_p=bx_p+1;
    for (i = 0; i < 36; i = i + 1) begin bytes[bx_p]=8'hEE;bx_p=bx_p+1; end
    bx_rem = bx_total; bx_p = 0;
    while (bx_rem > 0) begin
      bx_nfill = (bx_rem >= 8) ? 8 : bx_rem;
      bb0=bytes[bx_p+0]; bb1=(bx_nfill>1)?bytes[bx_p+1]:8'h00;
      bb2=(bx_nfill>2)?bytes[bx_p+2]:8'h00; bb3=(bx_nfill>3)?bytes[bx_p+3]:8'h00;
      bb4=(bx_nfill>4)?bytes[bx_p+4]:8'h00; bb5=(bx_nfill>5)?bytes[bx_p+5]:8'h00;
      bb6=(bx_nfill>6)?bytes[bx_p+6]:8'h00; bb7=(bx_nfill>7)?bytes[bx_p+7]:8'h00;
      // AXI-Stream first byte in lowest lane: bb0 -> tdata[7:0].
      s_send({bb7,bb6,bb5,bb4,bb3,bb2,bb1,bb0},
             (bx_nfill==8)?8'hFF:(bx_nfill==7)?8'h7F:(bx_nfill==6)?8'h3F:
             (bx_nfill==5)?8'h1F:(bx_nfill==4)?8'h0F:(bx_nfill==3)?8'h07:
             (bx_nfill==2)?8'h03:8'h01,
             (bx_nfill==bx_rem)?1'b1:1'b0);
      bx_p = bx_p + bx_nfill; bx_rem = bx_rem - bx_nfill;
    end
    // Wait for the parser to reject the packet (~80 cycles), monitoring
    // that M_AXIS never goes valid.
    for (bx_idle = 0; bx_idle < 80; bx_idle = bx_idle + 1) begin
      @(posedge aclk);
      if (m_axis_tvalid) begin
        $display("  M_AXIS leaked a byte for bad-session packet");
        errors = errors + 1;
      end
    end

    settle_stats;
    axi_read(5'h14, v0); check(v0 == 32'd1, "t5 ERROR_COUNT==1");
    axi_read(5'h00, v0); check(v0 == 32'd4, "t5 RX_PACKETS_LO==4 (dropped)");
    axi_read(5'h08, v0); check(v0 == 32'd5, "t5 RX_MESSAGES_LO==5 (no leak)");

    // ====================================================================
    // 6. M_AXIS backpressure
    // ====================================================================
    nmsgs = 1;  seq = 16'd7;  m0l = 36;
    for (i = 0; i < 36; i = i + 1)
      body0[i] = (i == 0) ? 8'h50 : 8'hE0 | i[7:0];
    exp_type = 8'h50; exp_base = 8'hE0; exp_lenlo = 8'h24;

    // Deassert M_AXIS TREADY, then feed the packet.  Once the parser
    // presents the first output byte, verify out_valid holds (stall),
    // then release TREADY and drain the message intact.
    @(negedge aclk);
    m_axis_tready <= 0;
    @(negedge aclk);

    fork
      begin : t6_prod
        pack_and_send;
      end
      begin : t6_wait
        while (!m_axis_tvalid) @(posedge aclk);
      end
    join
    check(m_axis_tvalid == 1'b1, "t6 out_valid holds under backpressure");
    check(m_axis_tvalid == 1'b1, "t6 out_valid still held (2)");
    // The DUT is holding the first output byte (0x00 = msg_len[15:8]) with
    // out_valid=1 and m_axis_tready=0.  Read that stalled byte now (it cannot
    // fire because TREADY is low), then release backpressure and drain the
    // remaining 37 bytes.  Without this, releasing TREADY would let the 0x00
    // beat fire before recv_check starts and the message would shift by one.
    begin : t6_lead
      reg [7:0] fb;
      reg        fl;
      m_recv(fb, fl);
      check(fb == 8'h00, "t6 lead byte is 0x00 (msg_len hi)");
      check(fl == 1'b0, "t6 lead byte TLAST==0");
    end
    // Release backpressure and drain the rest.
    m_axis_tready <= 1;
    @(posedge aclk);
    @(negedge aclk);

    skip_lead_zero = 1;
    recv_check(37);
    skip_lead_zero = 0;

    settle_stats;
    axi_read(5'h00, v0); check(v0 == 32'd5, "t6 RX_PACKETS_LO==5 (cum)");
    axi_read(5'h08, v0); check(v0 == 32'd6, "t6 RX_MESSAGES_LO==6 (cum)");
    axi_read(5'h14, v0); check(v0 == 32'd1, "t6 ERROR_COUNT==1");

    // ====================================================================
    // 6b. multi-byte session mismatch
    // ====================================================================
    // Every session byte differs here (0x57 0x52 0x4F 0x4E 0x47 0x30 0x30
    // 0x30 vs "NASDAQ01").  Guarantees the per-byte mismatch capture cannot
    // mask a mismatch behind a match on a later byte: all eight flags must
    // be set and the packet must still be rejected.  (test 5 only differs in
    // the first four bytes, so a byte-order bug in the slice mapping could
    // survive it.)
    bx_total = 8 + 2 + 2 + 2 + 36;
    bx_p = 0;
    bytes[bx_p]=8'h5A;bx_p=bx_p+1; bytes[bx_p]=8'h5A;bx_p=bx_p+1;
    bytes[bx_p]=8'h5A;bx_p=bx_p+1; bytes[bx_p]=8'h5A;bx_p=bx_p+1;
    bytes[bx_p]=8'h5A;bx_p=bx_p+1; bytes[bx_p]=8'h5A;bx_p=bx_p+1;
    bytes[bx_p]=8'h5A;bx_p=bx_p+1; bytes[bx_p]=8'h5A;bx_p=bx_p+1;
    bytes[bx_p]=8'h00;bx_p=bx_p+1; bytes[bx_p]=8'h06;bx_p=bx_p+1;
    bytes[bx_p]=8'h00;bx_p=bx_p+1; bytes[bx_p]=8'h01;bx_p=bx_p+1;
    bytes[bx_p]=8'h00;bx_p=bx_p+1; bytes[bx_p]=8'h24;bx_p=bx_p+1;
    for (i = 0; i < 36; i = i + 1) begin bytes[bx_p]=8'hEE;bx_p=bx_p+1; end
    bx_rem = bx_total; bx_p = 0;
    while (bx_rem > 0) begin
      bx_nfill = (bx_rem >= 8) ? 8 : bx_rem;
      bb0=bytes[bx_p+0]; bb1=(bx_nfill>1)?bytes[bx_p+1]:8'h00;
      bb2=(bx_nfill>2)?bytes[bx_p+2]:8'h00; bb3=(bx_nfill>3)?bytes[bx_p+3]:8'h00;
      bb4=(bx_nfill>4)?bytes[bx_p+4]:8'h00; bb5=(bx_nfill>5)?bytes[bx_p+5]:8'h00;
      bb6=(bx_nfill>6)?bytes[bx_p+6]:8'h00; bb7=(bx_nfill>7)?bytes[bx_p+7]:8'h00;
      s_send({bb7,bb6,bb5,bb4,bb3,bb2,bb1,bb0},
             (bx_nfill==8)?8'hFF:(bx_nfill==7)?8'h7F:(bx_nfill==6)?8'h3F:
             (bx_nfill==5)?8'h1F:(bx_nfill==4)?8'h0F:(bx_nfill==3)?8'h07:
             (bx_nfill==2)?8'h03:8'h01,
             (bx_nfill==bx_rem)?1'b1:1'b0);
      bx_p = bx_p + bx_nfill; bx_rem = bx_rem - bx_nfill;
    end
    for (bx_idle = 0; bx_idle < 80; bx_idle = bx_idle + 1) begin
      @(posedge aclk);
      if (m_axis_tvalid) begin
        $display("  M_AXIS leaked a byte for all-bytes-bad session packet");
        errors = errors + 1;
      end
    end
    settle_stats;
    axi_read(5'h00, v0); check(v0 == 32'd5, "t6b RX_PACKETS_LO==5 (unchanged)");
    axi_read(5'h08, v0); check(v0 == 32'd6, "t6b RX_MESSAGES_LO==6 (unchanged)");
    axi_read(5'h14, v0); check(v0 == 32'd2, "t6b ERROR_COUNT==2");

    // ====================================================================
    // 7. soft reset
    // ====================================================================
    axi_write(5'h18, 32'h3);   // CTRL.bit1=1 (soft reset), bit0 stays 1
    repeat (4) @(negedge aclk);   // let self-clearing pulse propagate
    axi_read(5'h00, v0); check(v0 == 32'd0, "sr RX_PACKETS_LO==0");
    axi_read(5'h08, v0); check(v0 == 32'd0, "sr RX_MESSAGES_LO==0");
    axi_read(5'h10, v0); check(v0 == 32'd0, "sr GAP_COUNT==0");
    axi_read(5'h14, v0); check(v0 == 32'd0, "sr ERROR_COUNT==0");
    axi_read(5'h18, v0); check(v0 == 32'd1, "sr CTRL==1 (enable kept, sr cleared)");

    // ====================================================================
    // 8. multi-packet sequential (3 packets, seq 1..3)
    // ====================================================================
    fork
      begin : t8_prod
        nmsgs = 1;  seq = 16'd1;  m0l = 36;
        for (i = 0; i < 36; i = i + 1) body0[i] = (i == 0) ? 8'd1 : (8'd1 | i[7:0]);
        pack_and_send;
        nmsgs = 1;  seq = 16'd2;  m0l = 36;
        for (i = 0; i < 36; i = i + 1) body0[i] = (i == 0) ? 8'd2 : (8'd2 | i[7:0]);
        pack_and_send;
        nmsgs = 1;  seq = 16'd3;  m0l = 36;
        for (i = 0; i < 36; i = i + 1) body0[i] = (i == 0) ? 8'd3 : (8'd3 | i[7:0]);
        pack_and_send;
      end
      begin : t8_cons
        integer pi;
        for (pi = 1; pi <= 3; pi = pi + 1) begin : t8_loop
          reg [7:0] t;
          reg [7:0] b;
          t = pi[7:0] + 8'd0;
          b = pi[7:0];
          exp_type = t;
          exp_base = b;
          exp_lenlo = 8'h24;
          recv_check(38);
        end
      end
    join

    settle_stats;
    axi_read(5'h00, v0); check(v0 == 32'd3, "t8 RX_PACKETS_LO==3");
    axi_read(5'h08, v0); check(v0 == 32'd3, "t8 RX_MESSAGES_LO==3");
    axi_read(5'h10, v0); check(v0 == 32'd0, "t8 GAP_COUNT==0");
    axi_read(5'h14, v0); check(v0 == 32'd0, "t8 ERROR_COUNT==0");

    // ====================================================================
    // 8b. back-to-back packets in one unbroken burst
    // ====================================================================
    // THE HARDWARE FAILURE MODE.  AXI DMA MM2S streams a whole file as one
    // continuous run of beats, so packet N+1's first beat can arrive while
    // the FSM is still parsing packet N.  On hardware this wedged the
    // reassembler: the FSM captured a packet length that excluded the final
    // beat (pkt_wr_ptr is updated by the same clock edge that raises
    // pkt_rx_done), finished the packet early, then misread the next
    // packet's bytes as a header and stalled with bytes_rem left over.
    //
    // Test 8 above uses a producer/consumer fork with M_AXIS drained in
    // step, so the FSM is always out of the way and the race never happens.
    // Here the beats are pushed with NO pause between packets and TREADY is
    // left high so the FSM is busy when the next packet starts arriving.
    begin : t8b
      integer pk, bi, nb;
      reg [7:0]  pb [0:63];
      reg [63:0] beat;
      integer keepn, k2;

      axi_write(5'h18, 32'h3);   // soft reset
      repeat (4) @(negedge aclk);
      axi_write(5'h18, 32'h1);   // enable

      exp_lenlo = 8'h24;
      exp_type  = 8'h41;
      exp_base  = 8'h00;

      // Producer and consumer run CONCURRENTLY: the producer keeps pushing
      // beats with no pause between packets while the consumer drains
      // M_AXIS, exactly as a real DMA feed + downstream pipeline behaves.
      // (Running them sequentially deadlocks: once the FSM owns the buffer
      // TREADY drops, and a blocking s_send can never make progress.)
      fork
        begin : t8b_prod
          for (pk = 0; pk < 3; pk = pk + 1) begin : pktloop
            pb[0]  = 8'h4E; pb[1] = 8'h41; pb[2] = 8'h53; pb[3] = 8'h44;
            pb[4]  = 8'h41; pb[5] = 8'h51; pb[6] = 8'h30; pb[7] = 8'h31;
            pb[8]  = 8'h00; pb[9] = pk[7:0] + 8'd1;   // seq = 1,2,3
            pb[10] = 8'h00; pb[11] = 8'h01;           // count = 1
            pb[12] = 8'h00; pb[13] = 8'h24;           // msg len = 36
            pb[14] = 8'h41;                           // type 'A'
            // recv_check convention: the body starts at pb[14].  Body byte j
            // (j = 0 is the type) must be exp_type for j = 0, and
            // exp_base | j for j >= 1 (exp_base = 0 here), which is exactly
            // what recv_check recomputes from the beat index.
            for (bi = 14; bi < 50; bi = bi + 1)
              pb[bi] = (bi == 14) ? 8'h41 : (bi - 8'd14);
            nb = 50;

            for (bi = 0; bi < nb; bi = bi + 8) begin : beatloop
              beat = 64'd0; keepn = 0;
              for (k2 = 0; k2 < 8; k2 = k2 + 1)
                if (bi + k2 < nb) begin
                  beat[8*k2 +: 8] = pb[bi + k2];
                  keepn = keepn + 1;
                end
              s_send(beat, (keepn == 8) ? 8'hFF :
                            (keepn == 7) ? 8'h7F : (keepn == 6) ? 8'h3F :
                            (keepn == 5) ? 8'h1F : (keepn == 4) ? 8'h0F :
                            (keepn == 3) ? 8'h07 : (keepn == 2) ? 8'h03 : 8'h01,
                     (bi + 8 >= nb) ? 1'b1 : 1'b0);
            end
          end
        end
        begin : t8b_cons
          recv_check(38);
          recv_check(38);
          recv_check(38);
        end
      join

      settle_stats;
      axi_read(5'h00, v0); check(v0 == 32'd3, "t8b RX_PACKETS_LO==3 (burst)");
      axi_read(5'h08, v1); check(v1 == 32'd3, "t8b RX_MESSAGES_LO==3 (burst)");
      axi_read(5'h10, v2); check(v2 == 32'd0, "t8b GAP_COUNT==0 (burst)");
      axi_read(5'h14, v3); check(v3 == 32'd0, "t8b ERROR_COUNT==0 (burst)");
    end

    // ====================================================================
    // 8c. long back-to-back burst over many packet boundaries
    // ====================================================================
    // THE HARDWARE WEDGE, reproduced.  The packet RAM is 4096 bytes and
    // pkt_wr_ptr is 12 bits, so if the FSM fails to claim the buffer between
    // packets the write pointer wraps and everything after it is garbage.  On
    // hardware 1 and 2 packets per DMA transfer worked while 3 or more left
    // bytes_rem stuck at 2040 with pkt_wr_ptr wrapped
    // (290 == (1463+1457+1466) mod 4096).
    //
    // This streams 8 packets with no inter-packet gap so a dropped TLAST
    // cannot hide behind an idle FSM.
    begin : t8c
      integer pk, bi, nb, k2, keepn;
      reg [7:0]  pb [0:63];
      reg [63:0] beat;

      axi_write(5'h18, 32'h3);
      repeat (4) @(negedge aclk);
      axi_write(5'h18, 32'h1);

      exp_lenlo = 8'h24;
      exp_type  = 8'h41;
      exp_base  = 8'h00;

      fork
        begin : t8c_prod
          for (pk = 0; pk < 8; pk = pk + 1) begin : pktloop
            pb[0] = 8'h4E; pb[1] = 8'h41; pb[2] = 8'h53; pb[3] = 8'h44;
            pb[4] = 8'h41; pb[5] = 8'h51; pb[6] = 8'h30; pb[7] = 8'h31;
            pb[8] = 8'h00; pb[9] = pk[7:0] + 8'd1;   // seq 1..8
            pb[10] = 8'h00; pb[11] = 8'h01;          // count = 1
            pb[12] = 8'h00; pb[13] = 8'h24;          // 36-byte message
            for (bi = 14; bi < 50; bi = bi + 1)
              pb[bi] = (bi == 14) ? 8'h41 : (bi - 8'd14);
            nb = 50;
            for (bi = 0; bi < nb; bi = bi + 8) begin : beatloop
              beat = 64'd0; keepn = 0;
              for (k2 = 0; k2 < 8; k2 = k2 + 1)
                if (bi + k2 < nb) begin
                  beat[8*k2 +: 8] = pb[bi + k2];
                  keepn = keepn + 1;
                end
              s_send(beat, (keepn == 8) ? 8'hFF :
                            (keepn == 7) ? 8'h7F : (keepn == 6) ? 8'h3F :
                            (keepn == 5) ? 8'h1F : (keepn == 4) ? 8'h0F :
                            (keepn == 3) ? 8'h07 : (keepn == 2) ? 8'h03 : 8'h01,
                     (bi + 8 >= nb) ? 1'b1 : 1'b0);
            end
          end
        end
        begin : t8c_cons
          recv_check(38);
          recv_check(38);
          recv_check(38);
          recv_check(38);
          recv_check(38);
          recv_check(38);
          recv_check(38);
          recv_check(38);
        end
      join

      settle_stats;
      axi_read(5'h00, v0); check(v0 == 32'd8, "t8c RX_PACKETS_LO==8 (long burst)");
      axi_read(5'h08, v1); check(v1 == 32'd8, "t8c RX_MESSAGES_LO==8 (long burst)");
      axi_read(5'h10, v2); check(v2 == 32'd0, "t8c GAP_COUNT==0 (long burst)");
      axi_read(5'h14, v3); check(v3 == 32'd0, "t8c ERROR_COUNT==0 (long burst)");
    end


    // ====================================================================
    // 9. final stat check
    // ====================================================================
    settle_stats;
    axi_read(5'h00, v0); axi_read(5'h04, v1);
    axi_read(5'h08, v2); axi_read(5'h0C, v3);
    axi_read(5'h10, v4); axi_read(5'h14, v5);
    axi_read(5'h18, v6);
    $display("FINAL: RX_PACKETS=%0d RX_MESSAGES=%0d GAP=%0d ERR=%0d CTRL=%0h",
             v0, v2, v4, v5, v6);
    check(v0 == 32'd8, "final RX_PACKETS_LO==8 (t8c last stage)");
    check(v1 == 32'd0, "final RX_PACKETS_HI==0");
    check(v2 == 32'd8, "final RX_MESSAGES_LO==8 (t8c last stage)");
    check(v3 == 32'd0, "final RX_MESSAGES_HI==0");
    check(v4 == 32'd0, "final GAP_COUNT==0");
    check(v5 == 32'd0, "final ERROR_COUNT==0");
    check(v6 == 32'd1, "final CTRL==1");

    if (errors == 0) begin
      $display("TB-ALL-PASS");
      $finish;
    end else begin
      $display("TB-FAILED %0d error(s)", errors);
      $finish;
    end
  end

endmodule
