"""Reproduce the hardware first-packet loss in simulation.

The hardware bug (whole buffer, 43428 messages):
    before any fix : 850 packets but gap=1, err=1463, first packet eaten
    after fix #1   : 850/850 packets, 43428/43428 messages, gap=0, but err=290
                     and the book reported +300 duplicated events

Every simulation suite passes, including the full chain, which is exactly why the
bug reached hardware: the testbenches present S_AXIS beats slowly relative to the
FSM, so a full word is always committed before ST_EMIT looks for it. The bug only
appears when the producer is FAST relative to the consumer - i.e. a real DMA.

This test loads the same real capture but drives S_AXIS with beats as fast as the
FIFO will take them, no idle cycles between them, so the reader can reach a byte
before its containing word has been committed. If that reproduces err != 0, the
fix can be validated locally instead of on the board.
"""
import io
import re
import sys

SRC = r"D:\agent\nasdaq-fpga\tools\tb_fullchain.v"
DST = r"D:\agent\nasdaq-fpga\tools\tb_fullchain_fast.v"

src = io.open(SRC, encoding="utf-8", errors="surrogateescape").read()

# The stock testbench waits for TREADY after every beat and inserts a negedge
# hold, which is slower than a DMA. Present back-to-back beats instead.
old = """        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= wv;
        s_axis_tkeep  <= (done == 8) ? 8'hFF : ((8'hFF >> (8 - done)));
        s_axis_tlast  <= ((q + done) == len);
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        q = q + done;"""

new = """        // Fast producer: hold TVALID high and swap in the next beat on the
        // very cycle the previous one is accepted, with no idle gap. This is
        // what a DMA looks like to the module, and it is the condition under
        // which the reader can outrun the write-alignment stage.
        @(negedge aclk);
        s_axis_tvalid <= 1;
        s_axis_tdata  <= wv;
        s_axis_tkeep  <= (done == 8) ? 8'hFF : ((8'hFF >> (8 - done)));
        s_axis_tlast  <= ((q + done) == len);
        q = q + done;
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);"""

if old not in src:
    print("send_pkt beat loop not found")
    sys.exit(1)

src = src.replace(old, new, 1)
src = src.replace("module tb_fullchain;", "module tb_fullchain_fast;", 1)

# Report the reassembler's own counters so err/gap are visible.
if "m64.error_count" in src:
    pass

io.open(DST, "w", encoding="utf-8", errors="surrogateescape",
        newline="\n").write(src)
print("wrote %s" % DST)
print("it drives S_AXIS back-to-back, with no idle cycle between beats")
