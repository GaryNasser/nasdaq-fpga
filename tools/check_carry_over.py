"""The "RTL identical between the two builds" claim obliges the report to note the defects carry over.

Section 1.z argues that the measured bitstream and the current source are functionally identical
because the four RTL modules match byte for byte. That is true and well evidenced.

It also means the RTL defects recorded in section 8 (items 10-12) are present in the MEASURED
bitstream, not introduced later. Round 132 added that sentence; this check keeps it, because the
argument in 1.z reads as reassuring and a reader could conclude the defects are new.

The check: wherever the report asserts the builds are equivalent/identical, it must also name the
defect items in the same passage.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
lines = rep.split("\n")

# Paragraphs that assert the two builds are equivalent.
EQUIV = re.compile(r"逐字节一致|功能上应当等价|约束改变的是时序解")
CARRIED = re.compile(r"同样存在于|一直在那里|缺陷.{0,20}带进")

print("passages asserting build equivalence")
print()
found = 0
fails = []
for i, l in enumerate(lines):
    if not EQUIV.search(l):
        continue
    found += 1
    # Look at a window around the assertion for the carry-over note.
    lo = max(0, i - 6)
    hi = min(len(lines), i + 30)
    window = "\n".join(lines[lo:hi])
    ok = bool(CARRIED.search(window))
    print("  L%-5d %s" % (i + 1, l.strip()[:72]))
    print("         carry-over note nearby: %s" % ok)
    if not ok:
        fails.append(i + 1)

print()
print("  %d equivalence passage(s)" % found)
print()
if found == 0:
    print("CARRY-OVER-FAIL (no equivalence passage found - the check would be vacuous)")
    sys.exit(1)

if fails:
    print("CARRY-OVER-FAIL (%d)" % len(fails))
    for f in fails:
        print("  line %d asserts equivalence without noting the defects carry over" % f)
    sys.exit(1)
print("CARRY-OVER-PASS (every equivalence claim states that the RTL defects carry over)")
