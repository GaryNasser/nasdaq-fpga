"""levels must equal the number of distinct PRICES among Add messages.

The C baseline allocates a level slot when it meets an unfamiliar price:

    for (i = 0; i < LEVELS - 1; i++)
        if (b->lev[i].valid && b->lev[i].price == price) { found = i; break; }

Bid and ask at the same price share a slot, so the count is over prices, not over (side, price).

    15,334 Add messages touch 95 distinct prices; the board and the baseline both print
    levels=95.

Two wrong groupings gave 3 and 20 before this one matched, which is why the check states the rule
it is testing rather than just the number.

Round 116 established this by hand; the check repeats it every run, so a capture swap or a changed
counter fails.
"""
import io
import os
import re
import struct
import sys

REPO = r"D:\agent\nasdaq-fpga"
RAW = os.path.join(REPO, "data", "itch_loc6836.raw")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

body = open(RAW, "rb").read()

prices = set()
adds = 0
i = 0
while i + 2 <= len(body):
    ln = struct.unpack(">H", body[i:i + 2])[0]
    if ln == 0 or i + 2 + ln > len(body):
        break
    m = body[i + 2:i + 2 + ln]
    if chr(m[0]) == "A" and ln == 36:
        adds += 1
        # ITCH 5.0 Add Order: price is the last 4 bytes, after the 8-byte symbol.
        prices.add(struct.unpack(">I", m[32:36])[0])
    i += 2 + ln

print("distinct prices among Add messages")
print()
print("  Add messages      %d" % adds)
print("  distinct prices   %d" % len(prices))
print()

rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
m = re.search(r"levels=(\d+)", rep)
if not m:
    print("LEVELS-DERIVE-FAIL (no levels= in the report)")
    sys.exit(1)

stated = int(m.group(1))
ok = (stated == len(prices))
print("  the report states levels=%d; the capture gives %d  %s"
      % (stated, len(prices), "ok" if ok else "MISMATCH"))

print()
print("  NOT checked here: orders=%s. Round 116 could not reproduce it; see the log."
      % (re.search(r"orders=(\d+)", rep).group(1)
         if re.search(r"orders=(\d+)", rep) else "?"))

print()
if not ok:
    print("LEVELS-DERIVE-FAIL (report %d, capture %d)" % (stated, len(prices)))
    sys.exit(1)
print("LEVELS-DERIVE-PASS (levels equals the distinct-price count of the capture)")
