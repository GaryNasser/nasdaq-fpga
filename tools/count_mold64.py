"""Verify the expected message count for itch_loc6836.mold64.

The --pipeline test asserts RX_MESSAGES == the count passed on the command
line. I have been passing 43428 from earlier notes; if that constant is wrong,
the test fails for a bookkeeping reason that has nothing to do with hardware.

This parses the MoldUDP64 file directly: each packet is
    [session 8][seq 2][count 2][ (len 2)(body len) ... count times ]
and counts the messages.
"""
import struct
import sys

PATH = r"D:\agent\nasdaq-fpga\data\itch_loc6836.mold64"


def parse(path):
    with open(path, "rb") as f:
        data = f.read()
    off = 0
    pkts = 0
    msgs = 0
    total_len_ok = 0
    total_len_bad = 0
    malformed = 0
    n = len(data)
    while off + 12 <= n:
        session = data[off:off + 8]
        seq = struct.unpack(">H", data[off + 8:off + 10])[0]
        count = struct.unpack(">H", data[off + 10:off + 12])[0]
        p = off + 12
        pkt_ok = True
        for _ in range(count):
            if p + 2 > n:
                pkt_ok = False
                break
            mlen = struct.unpack(">H", data[p:p + 2])[0]
            p += 2 + mlen
            if p > n:
                pkt_ok = False
                break
            msgs += 1
        if not pkt_ok:
            malformed += 1
            break
        pkts += 1
        off = p
    return pkts, msgs, malformed, off, n


pkts, msgs, malformed, consumed, total = parse(PATH)
print("file            : %s" % PATH)
print("bytes           : %d" % total)
print("packets parsed  : %d" % pkts)
print("messages        : %d" % msgs)
print("malformed       : %d" % malformed)
print("bytes consumed  : %d / %d" % (consumed, total))
print()
print("EXPECTED-MESSAGES %d" % msgs)
