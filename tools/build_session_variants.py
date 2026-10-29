"""Build one-session-byte-flipped captures LOCALLY, then copy them to the board.

The previous version wrote to /home/xilinx/... which does not exist on Windows. Files go to
data/sess_variants/ and are scp'd separately.

Base packet: 8 session + 2 seq + 2 count + 2 len + 36 message = 50 bytes.

    correct      'NASDAQ01'
    flip0..flip7 one low bit flipped per session byte

`err` is readable through AXI and counts rescan retries, so a variant whose err differs from the
others identifies the comparison the netlist gets wrong.
"""
import os
import struct

REPO = r"D:\agent\nasdaq-fpga"
OUT = os.path.join(REPO, "data", "sess_variants")

BASE_SESSION = b"NASDAQ01"


def build(session_bytes):
    pkt = bytearray()
    pkt += session_bytes
    pkt += struct.pack(">H", 1)
    pkt += struct.pack(">H", 1)
    pkt += struct.pack(">H", 36)
    pkt += b"A" + bytes(range(0x10, 0x10 + 35))
    assert len(pkt) == 50, len(pkt)
    return bytes(pkt)


os.makedirs(OUT, exist_ok=True)

variants = {"correct": BASE_SESSION}
for k in range(8):
    b = bytearray(BASE_SESSION)
    b[k] ^= 0x01
    variants["flip%d" % k] = bytes(b)

for name, sess in variants.items():
    data = build(sess)
    path = os.path.join(OUT, "_sess_%s.mold64" % name)
    with open(path, "wb") as f:
        f.write(data)
    print("%-10s session=%r  %d bytes  %s" % (name, sess, len(data), path))
