"""Check whether the MoldUDP64 count field agrees with the real byte lengths.

The RTL ends a packet when it has consumed `pkt_msg_rem` messages, where that
count is loaded from the packet's 2-byte count field. If the count field ever
disagrees with the actual number of messages present, the parser terminates at
the wrong byte and every following packet is misaligned.

Output is written to a file to avoid console encoding problems with bytes >127.
"""
import io
import struct

SRC = r"D:\agent\nasdaq-fpga\data\itch_loc6836.mold64"
OUT = r"D:\agent\nasdaq-fpga\tools\pkt_audit.txt"

data = open(SRC, "rb").read()


def walk(limit=None):
    off = 0
    idx = 0
    rows = []
    while off + 12 <= len(data):
        if limit is not None and idx >= limit:
            break
        sess = data[off:off + 8]
        seq = struct.unpack(">H", data[off + 8:off + 10])[0]
        cnt = struct.unpack(">H", data[off + 10:off + 12])[0]
        m = off + 12
        msgs = 0
        bad_len = 0
        for _ in range(cnt):
            if m + 2 > len(data):
                break
            ml = struct.unpack(">H", data[m:m + 2])[0]
            if ml == 0 or ml > 400:
                bad_len += 1
                break
            m += 2 + ml
            if m > len(data):
                break
            msgs += 1
        rows.append((idx, off, len(sess), seq, cnt, msgs, m - off, bad_len, sess))
        if msgs != cnt or bad_len:
            break
        off = m
        idx += 1
    return rows


rows = walk()
lines = []
lines.append("packets walked: %d" % len(rows))
bad = [r for r in rows if r[4] != r[5] or r[7]]
lines.append("packets where count != messages parsed: %d" % len(bad))
if bad:
    r = bad[0]
    lines.append("first mismatch: idx=%d off=%d seq=%d count=%d parsed=%d badlen=%d"
                 % (r[0], r[1], r[3], r[4], r[5], r[7]))

# Packet lengths seen
lens = [r[6] for r in rows]
if lens:
    lines.append("packet length min=%d max=%d" % (min(lens), max(lens)))

# Byte position where packet 277 starts, and 277 % 4096
if len(rows) > 277:
    r = rows[277]
    lines.append("")
    lines.append("packet 277: offset=%d  offset%%4096=%d  len=%d  count=%d  msgs=%d"
                 % (r[1], r[1] % 4096, r[6], r[4], r[5]))
if len(rows) > 276:
    r = rows[276]
    lines.append("packet 276: offset=%d  len=%d  count=%d  msgs=%d"
                 % (r[1], r[6], r[4], r[5]))

# Which offsets are not 8-aligned inside packets (message boundaries vs words)
mis = 0
for r in rows[:50]:
    if r[1] % 8 != 0:
        mis += 1
lines.append("first 50 packets whose start is not 8-byte aligned: %d" % mis)

open(OUT, "w", encoding="ascii").write("\n".join(lines) + "\n")
print("wrote", OUT)
