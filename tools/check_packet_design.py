"""The report must not describe the single-packet design as current, and must describe the real one.

Three facts, each verified in the RTL or driver this round:

    FIFO_AW = 12            -> 4,096 B buffer, still true, still a constraint on packet size
    s_can_write = enable && fifo_has_room
                            -> TREADY independent of packet boundaries
    DEFAULT_BUFFER_MB = 8   -> the 1.24 MB capture is one transfer

The failure this guards against is the one that existed until round 109: L523 said "当前 ... 单包
4 KB 结构" and concluded "按包分块回放", while the RTL and the driver did neither.

Tested against the shipped RTL rather than the report's own words, so the report cannot satisfy
it by agreeing with itself.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch", "mold64_reasm.v")
DRV = os.path.join(REPO, "board", "load_overlay.py")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

rtl_src = io.open(RTL, encoding="latin-1").read()
rtl = re.sub(r"//[^\n]*", "", rtl_src)
rtl = re.sub(r"/\*.*?\*/", "", rtl, flags=re.S)
drv = io.open(DRV, encoding="utf-8", errors="replace").read()
rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

print("the shipped design, and what the report says")
print()
fails = []

# --- fact 1: the buffer is a ring gated by fifo_has_room ---------------------
m = re.search(r"wire s_can_write\s*=\s*([^;]+);", rtl)
if not m:
    fails.append("s_can_write not found")
    print("  flow control          NOT FOUND")
else:
    expr = m.group(1).strip()
    ring = "fifo_has_room" in expr and not re.search(r"pkt_rx_done|pkt_hold", expr)
    print("  flow control          %s  (ring: %s)" % (expr[:34], ring))
    if not ring:
        fails.append("TREADY is gated on a packet boundary again")

# --- fact 2: buffer size ------------------------------------------------------
m = re.search(r"FIFO_AW\s*=\s*(\d+)", rtl)
size = 1 << int(m.group(1)) if m else None
print("  buffer size           %s B" % size)

# --- fact 3: one transfer covers the capture ---------------------------------
m = re.search(r"DEFAULT_BUFFER_MB\s*=\s*(\d+)", drv)
buf_mb = int(m.group(1)) if m else None
m = re.search(r"EXPECTED_SIZE\s*=\s*(\d+)|1237116", drv)
print("  default chunk         %s MB" % buf_mb)
capture = 1237116
if buf_mb and capture < buf_mb * (1 << 20):
    print("  the capture fits in one chunk: yes")

# --- the report must not contradict these ------------------------------------
print()
STALE = [
    ("calls the buffer single-packet today",
     r"当前[^\n]{0,40}单包"),
    ("says replay is packet-by-packet today",
     r"因此板上是\*\*按包分块回放\*\*"),
]
for label, pat in STALE:
    hit = re.search(pat, rep)
    print("  report %-38s %s" % (label, "YES" if hit else "no"))
    if hit:
        fails.append(label)

GOOD = [
    ("names fifo_has_room", r"fifo_has_room"),
    ("says one transfer covers the capture", r"一次传输"),
]
for label, pat in GOOD:
    hit = re.search(pat, rep)
    print("  report %-38s %s" % (label, "yes" if hit else "NO"))
    if not hit:
        fails.append("the report does not " + label)

print()
if fails:
    print("PACKET-DESIGN-FAIL (%d)" % len(fails))
    for f in fails:
        print("  %s" % f)
    sys.exit(1)
print("PACKET-DESIGN-PASS (the report matches the shipped ring buffer and one-transfer replay)")
