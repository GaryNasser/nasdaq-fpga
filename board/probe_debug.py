#!/usr/bin/env python3
"""Poll the DEBUG register during a replay - with the throttling round 152's first version lacked.

That version read MMIO in a tight daemon loop and wedged the board: an AXI4-Lite read from the ARM at
full speed starves the PS interconnect and SSH stops answering.

This one is deliberately slow:

    SLEEP_S      1 ms between samples, so the loop runs at about 1 kHz
    MAX_SAMPLES  a hard bound on memory and on the number of AXI transactions
    TIMEOUT_S    a wall-clock bound; the run gives up rather than hanging

### The question it answers

`word_committed` is not in the register map, but `pkt_wr_ptr` is (bits 20:9) along with `state`
(bits 4:0) and `byte_valid_r` (bit 8). So: at the moments the FSM is in a session state, how far ahead
was the writer?

If `pkt_wr_ptr >= 8` on every session-state sample, the word was already committed when the FSM moved,
`word_committed` was satisfied, and the guard had nothing to block - which explains why the rebuilt
bitstream changed no counter.

A 1.2 MB replay takes milliseconds, so this samples a coarse slice. That is sufficient for the question
and needs no speed.
"""
import sys
import threading
import time
from collections import Counter

import numpy as np
import pynq
from pynq import MMIO, Overlay

OVERLAY = "/home/xilinx/overlays/nasdaq/nasdaq.bit"
CAPTURE = "/home/xilinx/itch_loc6836.mold64"

REG_CTRL = 0x18
REG_DBG = 0x1C
SLEEP_S = 0.001
MAX_SAMPLES = 5000
TIMEOUT_S = 10.0

ol = Overlay(OVERLAY)
m64 = MMIO(ol.mold64_reasm_0.mmio.base_addr, 32)
dma = ol.axi_dma_0

samples = []
stop = threading.Event()


def poll():
    """Sample the DEBUG register slowly, bounded in count and time."""
    deadline = time.time() + TIMEOUT_S
    while not stop.is_set() and len(samples) < MAX_SAMPLES and time.time() < deadline:
        v = m64.read(REG_DBG)
        samples.append(((v >> 0) & 0x1F, (v >> 8) & 1, (v >> 9) & 0xFFF))
        time.sleep(SLEEP_S)


def main():
    m64.write(REG_CTRL, 0x2)          # soft reset
    time.sleep(0.001)
    m64.write(REG_CTRL, 0x1)          # enable
    time.sleep(0.05)

    t = threading.Thread(target=poll, daemon=True)
    t.start()

    data = open(CAPTURE, "rb").read()
    buf = pynq.allocate(shape=len(data), dtype="u1")
    buf[:] = np.frombuffer(data, dtype="u1")
    buf.flush()
    dma.sendchannel.transfer(buf)
    dma.sendchannel.wait()
    time.sleep(0.2)

    stop.set()
    t.join(timeout=3)
    buf.freebuffer()

    print("samples=%d (%.1f kHz, bounded by %d samples and %.0f s)"
          % (len(samples), 1.0 / SLEEP_S / 1000.0, MAX_SAMPLES, TIMEOUT_S))
    if not samples:
        print("no samples")
        return

    sess = [s for s in samples if 1 <= s[0] <= 8]
    print("session-state samples=%d" % len(sess))
    if sess:
        wrs = sorted(s[2] for s in sess)
        print("  pkt_wr_ptr: min=%d median=%d max=%d"
              % (wrs[0], wrs[len(wrs) // 2], wrs[-1]))
        ahead = sum(1 for s in sess if s[2] >= 8)
        print("  pkt_wr_ptr >= 8 : %d of %d (%.1f%%)"
              % (ahead, len(sess), 100.0 * ahead / len(sess)))
        print("  -> if this is near 100%%, the guard was satisfied before the FSM moved")
    else:
        print("  (the FSM was never caught in a session state - the replay is too short"
              " for a 1 kHz poller)")

    print("state histogram:", Counter(s[0] for s in samples).most_common(8))

    print()
    print("M64-STATS: rx_packets=%d rx_messages=%d gap=%d err=%d"
          % (m64.read(0x00), m64.read(0x08), m64.read(0x10), m64.read(0x14)))


if __name__ == "__main__":
    main()
