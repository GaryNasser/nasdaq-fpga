"""Inspect packet 277 of the capture - the first packet the RTL rejects.

The simulation reports the first parse error while starting packet index 277,
with the FIFO healthy and the byte position exactly aligned (writer 403259,
reader 401798, gap 1461 of 4096). So the parser is rejecting the CONTENT, not
reading the wrong bytes.

This dumps the packet's framing and per-message type bytes so the offending
construct is visible.
"""
import struct

PATH = r"D:\agent\nasdaq-fpga\data\itch_loc6836.mold64"


def packets(path):
    data = open(path, "rb").read()
    off = 0
    out = []
    while off + 12 <= len(data):
        cnt = struct.unpack(">H", data[off + 10:off + 12])[0]
        m = off + 12
        msgs = []
        for _ in range(cnt):
            ml = struct.unpack(">H", data[m:m + 2])[0]
            body = data[m + 2:m + 2 + ml]
            msgs.append((ml, body))
            m += 2 + ml
        out.append((off, m - off, data[off:off + 8], msgs))
        off = m
    return out


pk = packets(PATH)
print("total packets: %d" % len(pk))

for idx in (276, 277, 278):
    off, ln, sess, msgs = pk[idx]
    types = {}
    for ml, body in msgs:
        t = chr(body[0]) if body else "?"
        types[t] = types.get(t, 0) + 1
    print()
    print("packet idx %d: offset=%d len=%d session=%s count=%d"
          % (idx, off, ln, sess, len(msgs)))
    print("  message types: %s" % sorted(types.items()))
    for i, (ml, body) in enumerate(msgs[:6]):
        print("    msg %2d len=%d type=%r" % (i, ml, chr(body[0]) if body else "?"))

# Which types appear across the whole file?
alltypes = {}
for off, ln, sess, msgs in pk:
    for ml, body in msgs:
        t = chr(body[0]) if body else "?"
        alltypes[t] = alltypes.get(t, 0) + 1
print()
print("ALL message types in the file:")
for t in sorted(alltypes):
    print("  %r : %d" % (t, alltypes[t]))
