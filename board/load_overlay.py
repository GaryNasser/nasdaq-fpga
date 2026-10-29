#!/usr/bin/env python3
"""Board-side overlay load + verification for nasdaq overlays.

Modes:
  M1  --loopback   DMA loopback (specs/002): MM2S -> loopback -> S2MM,
                 verify byte-exact round-trip + throughput.
  M3  --pipeline   Parse pipeline (specs/003): MM2S -> mold64_reasm ->
                 itch_parse.  S2MM is unconnected; verify by reading the
                 reassembler + parser stat registers (packet/message counts).
  M7  --book       Full pipeline (specs/006): MM2S -> mold64_reasm ->
                 itch_parse -> order_book, with ts_hist measuring the
                 parser->book-commit latency.  Prints the book counters
                 (golden-answer compare against the C baseline) plus the
                 latency percentiles.

Contract:
  Exit codes: 0 = PASS, 2 = missing files / bad args,
              3 = overlay load failed, 4 = assertion failed

Usage:
  sudo -n env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python \
      /home/xilinx/overlays/nasdaq/load_overlay.py \
      --loopback  --input <packed_file> [--buffer-mb <N>]
  sudo -n env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python \
      /home/xilinx/overlays/nasdaq/load_overlay.py \
      --pipeline  --input <packed_file> --messages <N>
"""

import hashlib
import argparse
import os
import sys
import time

import numpy as np

try:
    import pynq
    from pynq import Overlay, MMIO
except ImportError:
    pynq = None  # --help works on non-board hosts; main() errors if used

OVERLAY_DIR = os.path.dirname(os.path.abspath(__file__))
BIT = os.path.join(OVERLAY_DIR, 'nasdaq.bit')
HWH = os.path.join(OVERLAY_DIR, 'nasdaq.hwh')

# Loopback_dma AXI4-Lite register offsets (M1)
REG_BYTES_IN_LO  = 0x00
REG_BYTES_IN_HI  = 0x04
REG_BYTES_OUT_LO = 0x08
REG_BYTES_OUT_HI = 0x0C
REG_DROP_COUNT   = 0x10
REG_ERROR_COUNT  = 0x14

# mold64_reasm AXI4-Lite register offsets (M3)
REG_M64_RX_PACKETS_LO   = 0x00
REG_M64_RX_PACKETS_HI   = 0x04
REG_M64_RX_MESSAGES_LO  = 0x08
REG_M64_RX_MESSAGES_HI  = 0x0C
REG_M64_GAP_COUNT       = 0x10
REG_M64_ERROR_COUNT     = 0x14
REG_M64_CTRL            = 0x18

# itch_parse AXI4-Lite register offsets (M3)
REG_IP_PARSE_CNT_LO  = 0x00
REG_IP_PARSE_CNT_HI  = 0x04
REG_IP_DROP_LEN_CNT  = 0x08
REG_IP_ERR_TYPE_CNT  = 0x0C
REG_IP_STOCK_DIR_CNT = 0x10
REG_IP_CTRL          = 0x14

# order_book AXI4-Lite register offsets (M4/M7)
REG_BOOK_CTRL        = 0x30
# Golden order-book counters for the single-stock subset
# (docs/measurements/baseline-a9.txt, stock_locate=6836, 43428 messages).
# The RTL reproduces these exactly in simulation - tools/tb_book.v, BOOK-PASS.
# Identity of the reference capture the golden counters were derived from.
# Matching on SIZE PLUS a checksum of the first kilobyte makes "is this the file
# the golden answers belong to?" a fact, not a guess.
REFERENCE_CAPTURE_SIZE = 1237116
REFERENCE_HEAD_SHA256_16 = "581378b01f9a1046"


def _is_reference_capture(path, total_bytes):
    """True when `path` is the single-stock capture the golden values describe."""
    if total_bytes != REFERENCE_CAPTURE_SIZE:
        return False
    try:
        with open(path, "rb") as f:
            head = f.read(1024)
    except OSError:
        return False
    return hashlib.sha256(head).hexdigest()[:16] == REFERENCE_HEAD_SHA256_16


GOLDEN_BOOK = {
    'add_cnt':  15334,
    'exe_cnt':      7,
    'can_cnt':  12518,
    'del_cnt':  15291,
    'rep_cnt':    238,
    'drop_cnt': 12826,
    'order_cnt':  320,
    'level_cnt':   95,
}

BOOK_REGS = {
    'order_cnt':  0x00, 'level_cnt':  0x04,
    'bid_price':  0x08, 'bid_shares': 0x0C,
    'ask_price':  0x10, 'ask_shares': 0x14,
    'add_cnt':    0x18, 'exe_cnt':    0x1C, 'can_cnt': 0x20,
    'del_cnt':    0x24, 'rep_cnt':    0x28, 'drop_cnt': 0x2C,
}

# ts_hist AXI4-Lite register offsets (M5/M7)
REG_TS_CTRL          = 0x00
REG_TS_DELTA         = 0x14
REG_TS_MIN           = 0x18
REG_TS_MAX           = 0x1C
REG_TS_SUM_LO        = 0x20
REG_TS_SUM_HI        = 0x24
REG_TS_COUNT_LO      = 0x28
REG_TS_COUNT_HI      = 0x2C
REG_TS_HIST_BASE     = 0x30
def _cycles_to_ns(cycles):
    """Convert PL timestamp-counter cycles to nanoseconds.

    Every ts_hist statistic - delta/min/max/sum and each histogram bucket - is a
    count of clock cycles. Keeping the conversion in one place stops the units
    drifting back into being labelled nanoseconds by accident.
    """
    return cycles * (1000.0 / PL_CLK_MHZ)


TS_HIST_BINS         = 256
# ts_hist assigns a bucket with bucket_idx = delta64_r[HIST_BIN_W+2:3], i.e. a
# right shift by 3, so each bucket spans TS_BIN_CYCLES *clock cycles*, not
# nanoseconds. This was previously named TS_BIN_NS = 8.0 and treated as ns,
# making every percentile 5.26x too small at 190 MHz.
TS_BIN_CYCLES        = 8
REG_TS_OVERFLOW      = 0x474
REG_TS_TSNOW         = 0x478   # free-running timestamp counter, low 32 bits
PL_CLK_MHZ           = 190.000   # design clock (clk_wiz_0: 100 MHz FCLK0 -> 190.000)
#                        MUST match DESIGN_FREQ in vivado/create_project.tcl.
#                        Was 200.0 after the clock was relaxed to 190 MHz for
#                        timing closure, which would have made every PL-derived
#                        rate 5.3% too high on hardware.

DEFAULT_BUFFER_MB = 8
MIN_THROUGHPUT_GBPS = 1.0  # 1 Gbps equivalent = 125 MB/s


def find_ip(ol, name_substring):
    """Find IP block base address by name substring in ip_dict."""
    for name, ip in ol.ip_dict.items():
        if name_substring in name:
            return ip.get('phys_addr') or ip.get('base_address')
    return None


def read64(mmio, lo_off, hi_off):
    """Read a 64-bit value as two 32-bit regs (little-endian)."""
    lo = mmio.read(lo_off)
    hi = mmio.read(hi_off)
    return (hi << 32) | lo


def _pipeline_test(ol, args) -> int:
    """M3 parse-pipeline test: enable mold64_reasm + itch_parse, stream
    MoldUDP64 packets via DMA MM2S, verify packet/message counts via stat
    registers.  S2MM is unconnected in M3 — no loopback, verify by count."""
    dma_base = find_ip(ol, 'axi_dma')
    m64_base = find_ip(ol, 'mold64_reasm')
    ip_base = find_ip(ol, 'itch_parse')
    book_base = find_ip(ol, 'order_book')

    if dma_base is None:
        print("FAIL-ASSERT: axi_dma_0 not found in ip_dict")
        return 4
    if m64_base is None:
        print("FAIL-ASSERT: mold64_reasm_0 not found in ip_dict")
        return 4
    if ip_base is None:
        print("FAIL-ASSERT: itch_parse_0 not found in ip_dict")
        return 4

    m64_mmio = MMIO(m64_base, 32)
    ip_mmio = MMIO(ip_base, 32)
    dma = getattr(ol, 'axi_dma_0', None)
    if dma is None:
        for attr in dir(ol):
            if 'axi_dma' in attr:
                dma = getattr(ol, attr)
                break
    if dma is None:
        print("FAIL-ASSERT: DMA object not accessible")
        return 4

    # Enable the WHOLE chain (CTRL bit0 = 1 on every stage).
    #
    # mold64_reasm and itch_parse alone are not enough: itch_parse holds
    # msg_latched until order_book asserts evt_ready. Leaving the book disabled
    # stops the chain draining, the 4 KB FIFO fills, TREADY drops, and the MM2S
    # transfer never completes - observed on the board as a hang inside
    # dma.sendchannel.wait().
    # Soft-reset the FIFO BEFORE enabling.
    #
    # The end-to-end path in this same file does this (CTRL 0x3) for a
    # reason: mold64_reasm's byte-FIFO carries state across runs. Streaming
    # into a FIFO left partly full by a previous interrupted replay starts
    # with a stale read pointer and fifo_has_room_r low, so the first transfer
    # can stall before a single byte is consumed. CTRL bit1 is the soft reset
    # and self-clears; bit0 stays asserted for the run.
    # ---- reset, then enable --------------------------------------------
    #
    # These MUST NOT be one write. CTL bit1 is a soft reset, and the commit
    # stage is registered:
    #
    #     word_ready = s_wr_fire && (avail >= 8)
    #     cm_valid  <= word_ready        -- RAM write happens one cycle later
    #     ... cleared by (!aresetn || soft_reset_pulse)
    #
    # so a reset pulse arriving in the cycle after a beat is accepted destroys
    # that word: taken off S_AXIS, never written to the RAM. Measured in
    # tools/tb_reset_seq.v: writing 0x3 (enable + reset) and starting the DMA
    # immediately loses one 8-byte word and the packet never parses (pkts=0,
    # err=39); writing 0x3, waiting, then 0x1 parses perfectly (pkts=1, err=0).
    #
    # On the board this cost the first packet of the first stream after an
    # overlay load - the "cold start" defect. Resetting first and only then
    # enabling removes it, with no warm-up packet needed.
    if args.legacy_reset:
        # The old, defective sequence: reset and enable in ONE write, with the
        # transfer starting immediately. Retained so the defect can be shown on
        # demand (expect the first packet's 8-word to vanish).
        m64_mmio.write(REG_M64_CTRL, 0x3)
        ip_mmio.write(REG_IP_CTRL, 0x1)
        if book_base is not None:
            book_mmio = MMIO(book_base, 64)
            book_mmio.write(REG_BOOK_CTRL, 0x1)
    else:
        m64_mmio.write(REG_M64_CTRL, 0x2)      # reset, enable held low
        ip_mmio.write(REG_IP_CTRL, 0x0)
        if book_base is not None:
            book_mmio = MMIO(book_base, 64)
            book_mmio.write(REG_BOOK_CTRL, 0x0)
        time.sleep(0.001)                      # let the pulse drain

        if getattr(args, 'reverse_enable', False):
            # consumers first, producer last
            if book_base is not None:
                book_mmio.write(REG_BOOK_CTRL, 0x1)
            ip_mmio.write(REG_IP_CTRL, 0x1)
            m64_mmio.write(REG_M64_CTRL, 0x1)
        else:
            m64_mmio.write(REG_M64_CTRL, 0x1)      # enable only
            ip_mmio.write(REG_IP_CTRL, 0x1)
            if book_base is not None:
                book_mmio.write(REG_BOOK_CTRL, 0x1)
        if book_base is None:
            print("WARN: order_book_0 not found; the chain cannot drain and the "
                  "DMA may stall")

    if getattr(args, 'settle', 0.0) > 0:
        time.sleep(args.settle)

    # Read input
    with open(args.input, 'rb') as f:
        data = f.read()
    total_bytes = len(data)
    expected_messages = args.messages
    buffer_size = args.buffer_mb * 1024 * 1024

    # Stream via DMA MM2S only (S2MM unconnected in M3)
    offset = 0
    t_start = time.monotonic()
    while offset < total_bytes:
        chunk_end = min(offset + buffer_size, total_bytes)
        chunk_len = chunk_end - offset

        send_buf = pynq.allocate(shape=chunk_len, dtype='u1')
        send_buf[:] = np.frombuffer(data[offset:chunk_end], dtype='u1')
        send_buf.flush()

        dma.sendchannel.transfer(send_buf)
        dma.sendchannel.wait()
        send_buf.freebuffer()
        offset = chunk_end

    t_xfer_end = time.monotonic()
    # Allow the pipeline to drain (parsing is faster than DMA at 190 MHz,
    # but give margin for the last packet's reassembly + decode).
    time.sleep(0.5)
    t_end = time.monotonic()

    # Read stat registers
    rx_packets = read64(m64_mmio, REG_M64_RX_PACKETS_LO, REG_M64_RX_PACKETS_HI)
    rx_messages = read64(m64_mmio, REG_M64_RX_MESSAGES_LO, REG_M64_RX_MESSAGES_HI)
    gap_count = m64_mmio.read(REG_M64_GAP_COUNT)
    m64_errors = m64_mmio.read(REG_M64_ERROR_COUNT)
    parse_cnt = read64(ip_mmio, REG_IP_PARSE_CNT_LO, REG_IP_PARSE_CNT_HI)
    drop_len = ip_mmio.read(REG_IP_DROP_LEN_CNT)
    err_type = ip_mmio.read(REG_IP_ERR_TYPE_CNT)

    elapsed = t_end - t_start
    # Round 257: `elapsed` contains a fixed 0.5 s drain sleep and per-chunk allocation, so dividing by it
    # measures patience, not the DMA path. Report the transfer loop separately.
    xfer = t_xfer_end - t_start
    throughput_mbps = total_bytes / xfer / 1e6 if xfer > 0 else 0.0
    wall_mbps = total_bytes / elapsed / 1e6 if elapsed > 0 else 0.0
    print(f"DMA-TIMING: transfer={xfer:.6f} s wall={elapsed:.6f} s drain={elapsed - xfer:.6f} s")
    print(f"DMA-RATE: dma={throughput_mbps:.1f} MB/s wall={wall_mbps:.2f} MB/s")

    # Assertions
    if gap_count != 0:
        print(f"FAIL-ASSERT: mold64 GAP_COUNT {gap_count} (expected 0)")
        return 4
    if m64_errors != 0:
        print(f"FAIL-ASSERT: mold64 ERROR_COUNT {m64_errors} (expected 0)")
        return 4
    # rx_packets was printed but never checked. For the single-stock subset the
    # value is known exactly (850) and every simulation run reports it, so an
    # enabled register should not be reported as mere information.
    if expected_messages == 43428 and rx_packets != 850:
        print(f"FAIL-ASSERT: mold64 RX_PACKETS {rx_packets} != 850 "
              f"(single-stock subset)")
        return 4
    if rx_messages != expected_messages:
        print(f"FAIL-ASSERT: mold64 RX_MESSAGES {rx_messages} != "
              f"expected {expected_messages}")
        return 4
    if parse_cnt != expected_messages:
        print(f"FAIL-ASSERT: itch PARSE_CNT {parse_cnt} != "
              f"expected {expected_messages}")
        return 4
    if drop_len != 0:
        print(f"FAIL-ASSERT: itch DROP_LEN_CNT {drop_len} (expected 0)")
        return 4

    print(f"PIPELINE-OK: {rx_packets} packets, {rx_messages} messages, "
          f"parse {parse_cnt}, 0 gaps, 0 errors, "
          f"{throughput_mbps:.1f} MB/s")
    return 0


def _count_mold64_messages(data: bytes) -> int:
    """Count messages in the project MoldUDP64 layout:
    [session:8][seq:2 BE][count:2 BE] per packet, then 2-byte lengths."""
    n = 0
    off = 0
    ln = len(data)
    while off + 12 <= ln:
        count = (data[off + 10] << 8) | data[off + 11]
        off += 12
        for _ in range(count):
            if off + 2 > ln:
                return n
            body = (data[off] << 8) | data[off + 1]
            off += 2 + body
            if off > ln:
                return n
            n += 1
    return n


def _hist_percentile(hist, pct):
    """Return the bucket upper edge (ns) at which `pct` percent of the samples
    have been accounted for.

    `hist` is a list of numpy int64 scalars (read back from MMIO), so the
    running sum must stay integral: `total * pct / 100.0` makes each `acc += c`
    promote to a Python float, and comparing float to numpy.int64 on this
    numpy version raises instead of coercing — historically leaving the loop
    spinning at 100% CPU for 20+ minutes after the capture had already
    completed.  Integer arithmetic (// 100) avoids the mixing entirely.
    """
    total = int(sum(int(c) for c in hist))
    if total == 0:
        return None
    target = (total * int(pct) + 99) // 100   # ceil, integer-only
    acc = 0
    for i, c in enumerate(hist):
        acc += int(c)
        if acc >= target:
            # Bucket i covers [i*8, (i+1)*8) cycles; report its upper edge in ns.
            return _cycles_to_ns((int(i) + 1) * TS_BIN_CYCLES)
    return _cycles_to_ns(len(hist) * TS_BIN_CYCLES)


def _book_test(ol, args) -> int:
    """M4/M5/M7 end-to-end replay: enable the whole pipeline, stream the file
    with one DMA MM2S transfer, then read the order-book counters and the
    latency histogram.  Prints a machine-parseable BOOK-RESULT line."""
    dma = getattr(ol, 'axi_dma_0', None)
    if dma is None:
        for attr in dir(ol):
            if 'axi_dma' in attr:
                dma = getattr(ol, attr)
                break
    m64_base = find_ip(ol, 'mold64_reasm')
    ip_base = find_ip(ol, 'itch_parse')
    book_base = find_ip(ol, 'order_book')
    ts_base = find_ip(ol, 'ts_hist')
    for name, base in (('axi_dma_0', dma), ('mold64_reasm_0', m64_base),
                       ('itch_parse_0', ip_base), ('order_book_0', book_base),
                       ('ts_hist_0', ts_base)):
        if base is None:
            print(f"FAIL-ASSERT: {name} not found in ip_dict")
            return 4
    if m64_base is None or ip_base is None or book_base is None or ts_base is None:
        return 4

    m64_mmio = MMIO(m64_base, 32)
    ip_mmio = MMIO(ip_base, 32)
    book_mmio = MMIO(book_base, 64)
    ts_mmio = MMIO(ts_base, 0x800)

    with open(args.input, 'rb') as f:
        data = f.read()
    total_bytes = len(data)
    nmsg = _count_mold64_messages(data)
    if nmsg == 0:
        print("FAIL-ARGS: no messages parsed from --input")
        return 2
    if total_bytes > args.buffer_mb * 1024 * 1024:
        print(f"FAIL-ARGS: input {total_bytes} B exceeds --buffer-mb "
              f"{args.buffer_mb} (use a smaller file or a larger buffer)")
        return 2

    # Enable the whole pipeline; ts_hist ctrl bit1 also clears its stats.
    m64_mmio.write(REG_M64_CTRL, 0x1)
    ip_mmio.write(REG_IP_CTRL, 0x1)
    book_mmio.write(REG_BOOK_CTRL, 0x1)
    ts_mmio.write(REG_TS_CTRL, 0x3)
    time.sleep(0.05)

    best = None
    best_pl = None
    last_cycles = 0
    for _ in range(args.repeat):
        # Reset the reassembler (counters + expected sequence) and parser, and
        # clear the histogram, so every pass starts from a clean pipeline.
        # The order book has no soft reset (CTRL bit1 is not implemented), so
        # on repeat > 1 its counters accumulate and the book state carries over
        # — run with --repeat 1 for the golden-answer comparison.
        # Reset FIRST, then enable. Never 0x3 immediately before a transfer:
        # the commit stage is registered, so a reset pulse landing one cycle
        # after a beat is accepted destroys that word (taken off S_AXIS, never
        # written). See tools/tb_reset_seq.v - 0x3-then-transfer loses a word
        # (pkts=0, err=39); reset, wait, enable parses correctly (err=0).
        #
        # --legacy-reset must reach THIS reset too: guarding only the preamble
        # let the book loop repair the defective write before the transfer, so
        # the failure the flag claims to demonstrate never occurred.
        if args.legacy_reset:
            m64_mmio.write(REG_M64_CTRL, 0x3)
        else:
            m64_mmio.write(REG_M64_CTRL, 0x2)
            time.sleep(0.001)
            m64_mmio.write(REG_M64_CTRL, 0x1)
        ip_mmio.write(REG_IP_CTRL, 0x1)
        # Re-assert the book enable every pass: all four blocks must be enabled
        # together for events to reach the book.  With the book left disabled
        # the parser stalls on evt_ready, the reassembler's M_AXIS backs up,
        # and the whole replay reports zeros (observed on hardware).
        book_mmio.write(REG_BOOK_CTRL, 0x1)
        ts_mmio.write(REG_TS_CTRL, 0x3)
        time.sleep(0.01)
        # np.frombuffer wraps the bytes object without a copy; assigning a raw
        # `bytes` object straight into a PYNQ buffer fails on this numpy
        # version ("invalid literal for int() with base 10").
        buf = pynq.allocate(shape=total_bytes, dtype='u1')
        buf[:] = np.frombuffer(data, dtype='u1')
        buf.flush()
        # Bracket the transfer with PL timestamp-counter reads so the rate can
        # also be reported against the *PL* clock.  The wall-clock figure that
        # dma.sendchannel.wait() yields is the host/DMA round trip (buffer
        # alloc + flush + driver overhead); the PL window shows what the
        # pipeline itself had to chew through.
        ts_before = ts_mmio.read(REG_TS_TSNOW)
        t0 = time.monotonic()
        dma.sendchannel.transfer(buf)
        dma.sendchannel.wait()
        t1 = time.monotonic()
        ts_after = ts_mmio.read(REG_TS_TSNOW)
        cycles = (ts_after - ts_before) & 0xFFFFFFFF
        # TSNOW is 32-bit, so its modular difference is correct only while a
        # transfer stays under one wrap (2^32 / PL_CLK_MHZ = 22.6 s at 190 MHz).
        # read64()'s LO-then-HI pairs can also tear if a counter is still
        # advancing. Both corruption modes show up as a cycle count grossly
        # larger than the wall-clock window, so check against that: the PL is
        # never slower than the host, so wall seconds bound it from above.
        wall_cycles_max = (t1 - t0) * PL_CLK_MHZ * 1e6 * 1.5 + 1e6
        if cycles > wall_cycles_max:
            print(f"WARN-IMPLAUSIBLE: TSNOW delta {cycles} cycles exceeds the "
                  f"{(t1 - t0) * 1e3:.1f} ms wall window "
                  f"(bound {wall_cycles_max:.0f}); PL rate for this pass is "
                  f"unreliable - treat ts_hist/rate figures with suspicion")
        buf.freebuffer()
        dt = t1 - t0
        rate = nmsg / dt if dt > 0 else 0.0
        pl_rate = (nmsg / (cycles / (PL_CLK_MHZ * 1e6))
                   if cycles > 0 else 0.0)
        best = rate if best is None else max(best, rate)
        best_pl = pl_rate if best_pl is None else max(best_pl, pl_rate)
        last_cycles = cycles

    time.sleep(0.2)   # let the last event drain through the book FSM

    counters = {k: book_mmio.read(v) for k, v in BOOK_REGS.items()}
    # The parser's own counters (round 138): they distinguish "the parser emitted nothing" from
    # "the parser emitted and the book ignored it" - the question round 137 left open.
    ip_parse_cnt = read64(ip_mmio, 0x00, 0x04)
    ip_drop_len = ip_mmio.read(0x08)
    ip_err_type = ip_mmio.read(0x0C)
    # _book_test checked neither of these before - it relied on the book
    # counters as an indirect proxy for a clean run.
    rx_packets = read64(m64_mmio, REG_M64_RX_PACKETS_LO, REG_M64_RX_PACKETS_HI)
    rx_messages = read64(m64_mmio, REG_M64_RX_MESSAGES_LO, REG_M64_RX_MESSAGES_HI)
    gap_count = m64_mmio.read(REG_M64_GAP_COUNT)
    m64_errors = m64_mmio.read(REG_M64_ERROR_COUNT)
    ts_count = read64(ts_mmio, REG_TS_COUNT_LO, REG_TS_COUNT_HI)
    ts_sum = read64(ts_mmio, REG_TS_SUM_LO, REG_TS_SUM_HI)
    hist = [ts_mmio.read(REG_TS_HIST_BASE + 4 * i)
            for i in range(TS_HIST_BINS)]

    print(f"BOOK-RESULT: messages={nmsg} bytes={total_bytes} "
          f"seconds={nmsg / best if best else 0:.6f} msg_per_s={best or 0:.0f}")
    # PL-side view: window measured by the PL's own 190 MHz timestamp
    # counter, so it is independent of host scheduling and DMA setup.
    pl_s = (last_cycles / (PL_CLK_MHZ * 1e6)) if last_cycles else 0.0
    print(f"BOOK-PL-RATE: cycles={last_cycles} pl_seconds={pl_s:.6f} "
          f"msg_per_s={(nmsg / pl_s) if pl_s > 0 else 0:.0f} "
          f"mb_per_s={(total_bytes / pl_s / 1e6) if pl_s > 0 else 0:.1f}")
    print("BOOK-COUNTERS: " + " ".join(f"{k}={v}" for k, v in counters.items()))
    print(f"IP-STATS: parse_cnt={ip_parse_cnt} drop_len={ip_drop_len} err_type={ip_err_type}")
    print(f"M64-STATS: rx_packets={rx_packets} rx_messages={rx_messages} "
          f"gap={gap_count} err={m64_errors}")
    ts_min = ts_mmio.read(REG_TS_MIN)
    ts_max = ts_mmio.read(REG_TS_MAX)
    # ts_hist counters are CYCLES. Print both units so a later reader
    # cannot mistake one for the other - the original code labelled
    # cycles as ns, understating latency by 5.26x at 190 MHz.
    # (see TS_BIN_CYCLES)
    print(f"TS-STATS: count={ts_count} "
          f"min_cyc={ts_min} max_cyc={ts_max} "
          f"mean_cyc={(ts_sum / ts_count) if ts_count else 0:.1f} "
          f"min_ns={_cycles_to_ns(ts_min):.1f} "
          f"max_ns={_cycles_to_ns(ts_max):.1f} "
          f"mean_ns={_cycles_to_ns(ts_sum / ts_count) if ts_count else 0:.1f} "
          f"p50_ns={_hist_percentile(hist, 50)} "
          f"p95_ns={_hist_percentile(hist, 95)} "
          f"p99_ns={_hist_percentile(hist, 99)} "
          f"overflow={ts_mmio.read(REG_TS_OVERFLOW)}")

    # Verify against the golden answer. Until now this function ended with an
    # unconditional `return 0`, so on hardware ANY book content - including an
    # entirely wrong one - reported success. Every other check in this driver
    # asserts; the one that validates the reconstructed book did not.

    # A gap or a reassembly error is a parsing fault regardless of what the book
    # happens to contain, and both registers are already read above.
    if gap_count != 0:
        print(f"FAIL-ASSERT: mold64 GAP_COUNT {gap_count} (expected 0)")
        return 4
    if m64_errors != 0:
        print(f"FAIL-ASSERT: mold64 ERROR_COUNT {m64_errors} (expected 0)")
        return 4
    if getattr(args, 'no_golden', False):
        print("GOLDEN-SKIPPED: --no-golden given")
        return 0
    if nmsg != 43428:
        # Distinguish "the user chose another input" from "the expected input
        # produced the wrong message count". The latter is a FAILURE - it means
        # the file was truncated or corrupted, or the reassembler lost messages -
        # and reporting it as a skip would defeat the whole comparison.
        ref = _is_reference_capture(args.input, total_bytes)
        if ref:
            print(f"FAIL-ASSERT: parsed {nmsg} messages from the reference "
                  f"capture, expected 43428 - the file is truncated or the "
                  f"reassembler lost messages")
            return 6
        print(f"GOLDEN-SKIPPED: {nmsg} messages, golden expects 43428 "
              f"(different input - pass --no-golden to silence)")
        return 0
    if args.repeat > 1:
        # The counters below are read once, after every replay, and order_book
        # has no soft reset, so they hold --repeat x the golden values. Report
        # that plainly rather than as FAIL-GOLDEN with all eight "wrong".
        print(f"GOLDEN-SKIPPED: --repeat {args.repeat} accumulates the book "
              f"counters (order_book has no soft reset); use --repeat 1 for the "
              f"golden-answer comparison")
        return 0

    if rx_packets != 850:
        print(f"FAIL-ASSERT: mold64 RX_PACKETS {rx_packets} != 850 "
              f"(single-stock subset)")
        return 4

    bad = []
    for name, want in GOLDEN_BOOK.items():
        got = counters.get(name)
        if got != want:
            bad.append(f"{name}={got} (want {want})")
    if bad:
        print("FAIL-GOLDEN: " + ", ".join(bad))
        return 5
    print("GOLDEN-OK: all %d book counters match the A9 baseline" % len(GOLDEN_BOOK))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Nasdaq overlay verification')
    parser.add_argument('--loopback', action='store_true',
                        help='M1 only: DMA loopback through the M1 loopback_dma IP. '
                             'NOT available on this overlay - the current block '
                             'design does not instantiate loopback_dma, so this mode '
                             'exits 4. Use --book or --pipeline here.')
    parser.add_argument('--pipeline', action='store_true',
                        help='M3: parse pipeline test (verify via stat registers)')
    parser.add_argument('--book', action='store_true',
                        help='M7: full pipeline + order book + latency histogram')
    parser.add_argument('--input', type=str, default=None,
                        help='Packed MoldUDP64 file')
    parser.add_argument('--messages', type=int, default=None,
                        help='M3: expected message count in the packed file')
    parser.add_argument('--repeat', type=int, default=1,
                        help='M7: repeat the DMA replay N times for throughput '
                             '(book counters accumulate; use 1 for golden-answer)')
    parser.add_argument('--no-golden', action='store_true',
                        help='M7: skip the golden book-counter comparison '
                             '(use for inputs other than the single-stock subset)')
    parser.add_argument('--legacy-reset', action='store_true',
                        help='use the old single-write CTRL=0x3 reset+enable; '
                             'this loses one 8-byte word from the first packet '
                             '(kept to demonstrate the defect)')
    parser.add_argument('--reverse-enable', action='store_true',
                        help='enable order_book first, then itch_parse, then '
                             'mold64_reasm. Round 139 hypothesis: enabling the '
                             'producer first means its output stalls while the '
                             'consumer is still off, and a stalled output '
                             'corrupts the reassembler read state.')
    parser.add_argument('--settle', type=float, default=0.0,
                        help='seconds to wait AFTER enabling the chain and BEFORE the '
                             'DMA starts. Round 137 hypothesis: the three enable writes '
                             'are separate AXI transactions, and the first packet is '
                             'consumed while the parser/book are still off.')
    parser.add_argument('--buffer-mb', type=int, default=DEFAULT_BUFFER_MB,
                        help=f'DMA buffer size in MB (default {DEFAULT_BUFFER_MB})')
    args = parser.parse_args()

    modes = [args.loopback, args.pipeline, args.book]
    if sum(1 for m in modes if m) > 1:
        print("FAIL-ARGS: --loopback, --pipeline and --book are mutually exclusive")
        return 2
    if not any(modes):
        # Default: just load the overlay (no test)
        pass

    # ---- file pair check ---------------------------------------------------
    missing = [f for f in (BIT, HWH) if not os.path.exists(f)]
    if missing:
        print(f"FAIL-FILES: missing {' and '.join(missing)}")
        return 2

    if args.loopback and not args.input:
        print("FAIL-ARGS: --input required for --loopback")
        return 2
    if args.pipeline:
        if not args.input:
            print("FAIL-ARGS: --input required for --pipeline")
            return 2
        if args.messages is None or args.messages <= 0:
            print("FAIL-ARGS: --messages (positive int) required for --pipeline")
            return 2
    if args.book:
        if not args.input:
            print("FAIL-ARGS: --input required for --book")
            return 2
        if args.repeat < 1:
            print("FAIL-ARGS: --repeat must be >= 1")
            return 2

    # ---- load overlay ------------------------------------------------------
    if pynq is None:
        print("FAIL-LOAD: pynq not available — "
              "run on board with pynq-venv")
        return 3
    try:
        ol = Overlay(BIT)
        ol.download()
    except PermissionError as e:
        print(f"FAIL-LOAD: permission error ({e}); "
              f"use: sudo -n env XILINX_XRT=/usr "
              f"/usr/local/share/pynq-venv/bin/python")
        return 3
    except Exception as e:  # noqa: BLE001
        print(f"FAIL-LOAD: {type(e).__name__}: {e}")
        return 3

    if not any(modes):
        print("PASS: overlay loaded (no test requested)")
        return 0

    # ---- M7 book replay ----------------------------------------------------
    if args.book:
        return _book_test(ol, args)

    # ---- M3 pipeline test --------------------------------------------------
    if args.pipeline:
        return _pipeline_test(ol, args)

    # ---- M1 loopback test --------------------------------------------------
    # ---- locate DMA + loopback_dma -----------------------------------------
    dma_base = find_ip(ol, 'axi_dma')
    loopback_base = find_ip(ol, 'loopback_dma')

    if dma_base is None:
        print("FAIL-ASSERT: axi_dma_0 not found in ip_dict")
        return 4
    if loopback_base is None:
        # This is not a bitstream fault: the current block design is the M2-M5 chain
        # and has no loopback_dma IP. Say so, or the reader concludes the overlay is
        # broken.
        print("FAIL-ASSERT: loopback_dma_0 not found in ip_dict")
        print("  --loopback needs the M1 loopback overlay; the current block design "
              "does not instantiate loopback_dma.")
        print("  Use --book or --pipeline on this overlay.")
        return 4

    try:
        loopback_mmio = MMIO(loopback_base, 32)
        dma = getattr(ol, 'axi_dma_0', None)
        if dma is None:
            # Try alternate naming
            for attr in dir(ol):
                if 'axi_dma' in attr:
                    dma = getattr(ol, attr)
                    break
        if dma is None:
            print("FAIL-ASSERT: DMA object not accessible via ol.axi_dma_0")
            return 4
    except Exception as e:  # noqa: BLE001
        print(f"FAIL-ASSERT: DMA init failed: {e}")
        return 4

    # ---- read input file ---------------------------------------------------
    try:
        with open(args.input, 'rb') as f:
            data = f.read()
    except Exception as e:  # noqa: BLE001
        print(f"FAIL-ASSERT: cannot read input file: {e}")
        return 4

    total_bytes = len(data)
    buffer_size = args.buffer_mb * 1024 * 1024

    # ---- DMA loopback: chunked transfer ------------------------------------
    recv_buf = bytearray(total_bytes)
    mismatches = 0
    t_start = time.monotonic()

    offset = 0
    while offset < total_bytes:
        chunk_end = min(offset + buffer_size, total_bytes)
        chunk = data[offset:chunk_end]
        chunk_len = len(chunk)

        try:
            send_buf = pynq.allocate(shape=chunk_len, dtype='u1')
            recv_buf_chunk = pynq.allocate(shape=chunk_len, dtype='u1')
        except Exception as e:  # noqa: BLE001
            print(f"FAIL-ASSERT: DMA buffer allocation failed ({e}); "
                  f"try smaller --buffer-mb (current={args.buffer_mb})")
            return 4

        send_buf[:] = np.frombuffer(chunk, dtype='u1')
        send_buf.flush()

        try:
            dma.sendchannel.transfer(send_buf)
            dma.recvchannel.transfer(recv_buf_chunk)
            dma.sendchannel.wait()
            dma.recvchannel.wait()
        except Exception as e:  # noqa: BLE001
            print(f"FAIL-ASSERT: DMA transfer failed at offset {offset}: {e}")
            return 4

        recv_buf_chunk.invalidate()
        recv_buf[offset:chunk_end] = bytes(recv_buf_chunk)

        send_buf.freebuffer()
        recv_buf_chunk.freebuffer()

        # Verify this chunk immediately
        for i in range(chunk_len):
            if recv_buf[offset + i] != data[offset + i]:
                mismatches += 1

        offset = chunk_end

    t_end = time.monotonic()
    elapsed = t_end - t_start
    throughput_mbps = total_bytes / elapsed / 1e6
    throughput_gbps = throughput_mbps * 8 / 1000

    # ---- read loopback stats ----------------------------------------------
    bytes_in = read64(loopback_mmio, REG_BYTES_IN_LO, REG_BYTES_IN_HI)
    bytes_out = read64(loopback_mmio, REG_BYTES_OUT_LO, REG_BYTES_OUT_HI)
    drop_count = loopback_mmio.read(REG_DROP_COUNT)
    error_count = loopback_mmio.read(REG_ERROR_COUNT)

    # ---- assertions --------------------------------------------------------
    if bytes_in != total_bytes:
        print(f"FAIL-ASSERT: BYTES_IN {bytes_in} != expected {total_bytes}")
        return 4
    if bytes_out != total_bytes:
        print(f"FAIL-ASSERT: BYTES_OUT {bytes_out} != expected {total_bytes}")
        return 4
    if drop_count != 0:
        print(f"FAIL-ASSERT: DROP_COUNT {drop_count} (expected 0)")
        return 4
    if error_count != 0:
        print(f"FAIL-ASSERT: ERROR_COUNT {error_count} (expected 0)")
        return 4
    if mismatches != 0:
        print(f"FAIL-ASSERT: {mismatches} byte mismatches in loopback")
        return 4
    if throughput_gbps < MIN_THROUGHPUT_GBPS:
        print(f"FAIL-ASSERT: throughput {throughput_gbps:.2f} Gbps "
              f"< {MIN_THROUGHPUT_GBPS} Gbps minimum")
        return 4

    print(f"LOOPBACK-OK: {total_bytes} bytes, 0 mismatches, 0 drops, "
          f"{throughput_mbps:.1f} MB/s ({throughput_gbps:.2f} Gbps)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
