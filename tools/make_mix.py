"""Build a message-length experiment input in the framing the reassembler actually accepts.

Round 5 failed because my rebuilt capture dropped the per-packet session header. `test_3pkt.mold64` proves the
required layout:

    every packet:  8 B session ("NASDAQ01") + 2 B seq + 2 B count + count x (2 B length + payload)

**This repository's captures repeat the session on every packet.** The standard says once; the hardware and every
existing file say every packet. Follow the files.

### The experiment

ITCH message length depends on type: A=36, D=19, X=23, P=44, U=35.

    long    A + P + U     ~35.9 B/msg
    short   D + X         ~20.2 B/msg

Same byte budget, message counts differing by ~78%. If the limiter is per-message, the SHORT stream should show a
lower byte rate. If it is per-byte, both should show the same rate.
"""
import io
import os
import struct
import sys

REPO = r"D:\agent\nasdaq-fpga"
SRC = os.path.join(REPO, "data", "itch_1m.mold64")
DATA = os.path.join(REPO, "data")
LIMIT = 3_800_000          # under the 4,194,303 B DMA cap, with headroom

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SESSION = b"NASDAQ01"


def read_packets(path):
    """Read packets, accepting a session header on every packet."""
    b = io.open(path, "rb").read()
    off = 0
    pkts = []
    while off + 12 <= len(b):
        if b[off:off + 8] != SESSION:
            raise SystemExit("session header not found at offset %d" % off)
        seq, cnt = struct.unpack(">HH", b[off + 8:off + 12])
        off += 12
        msgs = []
        for _ in range(cnt):
            if off + 2 > len(b):
                break
            ln = struct.unpack(">H", b[off:off + 2])[0]
            msgs.append(b[off + 2:off + 2 + ln])
            off += 2 + ln
        if msgs:
            pkts.append((seq, msgs))
    return pkts


def write_filtered(pkts, keep, dst, limit=LIMIT):
    """Emit only packets whose kept messages fit the budget, with a session header on every packet."""
    out = bytearray()
    seq = 1
    nmsg = 0
    nbyte = 0
    for _, msgs in pkts:
        sel = [m for m in msgs if m and chr(m[0]) in keep]
        if not sel:
            continue
        size = 12 + sum(2 + len(m) for m in sel)
        if len(out) + size > limit:
            break
        out += SESSION
        out += struct.pack(">HH", seq, len(sel))
        for m in sel:
            out += struct.pack(">H", len(m))
            out += m
            nmsg += 1
            nbyte += len(m)
        seq += 1
    io.open(dst, "wb").write(bytes(out))
    return len(out), nmsg, seq - 1, (nbyte / nmsg if nmsg else 0.0)


pkts = read_packets(SRC)
print("source packets: %d" % len(pkts))

for name, keep in (("long", set("APU")), ("short", set("DX"))):
    dst = os.path.join(DATA, "exp_%s.mold64" % name)
    size, nmsg, npkt, mean = write_filtered(pkts, keep, dst)
    print("  %-6s %-20s %8d B  %7d msgs  %5d pkts  mean %5.2f B"
          % (name, os.path.basename(dst), size, nmsg, npkt, mean))

# Verify the emitted files parse back with the same reader.
print()
for name in ("long", "short"):
    p = os.path.join(DATA, "exp_%s.mold64" % name)
    back = read_packets(p)
    total = sum(len(m) for _, ms in back for m in ms)
    n = sum(len(ms) for _, ms in back)
    print("  verify %-6s %5d packets  %7d msgs  mean %5.2f B  (round-trips)"
          % (name, len(back), n, total / n if n else 0))
