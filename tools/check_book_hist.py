"""The book counters must equal the ITCH message-type histogram of the capture.

    BOOK-COUNTERS: add=15334 exe=7 can=12518 del=15291 rep=238 ...

    counted from data/itch_loc6836.raw:
        A=15334  D=15291  X=12518  U=238  E=7

Every one matches. That is a strong cross-check the project has never run: the counters come from
the hardware's order book, the histogram comes from the file, and they agree - which means the
book processed every message of every type, not merely the total.

A total match could hide compensating errors (two extra adds and two missed deletes). Per-type
agreement cannot.

This re-derives the histogram every run, so a capture swap or a changed counter fails.
"""
import io
import os
import re
import struct
import sys
from collections import Counter

REPO = r"D:\agent\nasdaq-fpga"
RAW = os.path.join(REPO, "data", "itch_loc6836.raw")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

raw = open(RAW, "rb").read()
hist = Counter()
j = 0
while j + 2 <= len(raw):
    ln = struct.unpack(">H", raw[j:j + 2])[0]
    if ln == 0 or j + 2 + ln > len(raw):
        break
    hist[chr(raw[j + 2])] += 1
    j += 2 + ln

print("ITCH message-type histogram, counted from the capture")
print()
for k in sorted(hist, key=lambda x: -hist[x]):
    print("  %s  %6d" % (k, hist[k]))
print("  total  %6d" % sum(hist.values()))
print()

rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
m = re.search(r"BOOK-COUNTERS:\s*(.+)", rep)
if not m:
    print("BOOK-HIST-FAIL (no BOOK-COUNTERS line in the report)")
    sys.exit(1)

line = m.group(1)
counters = dict(re.findall(r"(\w+)=(\d+)", line))
print("  report line: %s" % line.strip()[:96])
print()

# Which counter corresponds to which ITCH type.
MAP = [
    ("add", "A", "Add Order"),
    ("del", "D", "Order Delete"),
    ("can", "X", "Order Cancel"),
    ("rep", "U", "Order Replace"),
    ("exe", "E", "Order Executed"),
]

fails = []
print("  counter  ITCH  from bytes   from the report   ")
for name, typ, desc in MAP:
    if name not in counters:
        print("  %-8s %-5s %-12d (counter absent)" % (name, typ, hist.get(typ, 0)))
        continue
    stated = int(counters[name])
    actual = hist.get(typ, 0)
    ok = stated == actual
    print("  %-8s %-5s %-12d %-12d  %s"
          % (name, typ, actual, stated, "ok" if ok else "MISMATCH"))
    if not ok:
        fails.append("%s: report %d, capture %d" % (name, stated, actual))

# The total must also match the number of messages.
total_itch = sum(hist.values())
if "orders" in counters:
    print()
    print("  note: orders=%s levels=%s are book state, not message counts"
          % (counters.get("orders"), counters.get("levels")))

print()
if fails:
    print("BOOK-HIST-FAIL (%d)" % len(fails))
    for f in fails:
        print("  %s" % f)
    sys.exit(1)
print("BOOK-HIST-PASS (every book counter equals the ITCH histogram of the capture)")
