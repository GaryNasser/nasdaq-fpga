"""Every mention of 200 MHz must be marked as historical. 190 MHz is the shipped frequency.

The design ran at 200 MHz in early rounds and at 190 MHz since round 37. The report mentions both
- legitimately, because several corrections are ABOUT the frequency change - and each 200 MHz
mention must say so, or a reader takes the wrong clock.

The five current mentions all carry their context:

    L332    "注释里曾写 ... 实测是 +335 ps"             曾写 = was written
    L517    "PL 时钟实测（早期构建）... 当前 bitstream 为 190 MHz"
    L552    "该构建 200 MHz ... 当前 190 MHz 构建为 5.26 ns"
    L807    "驱动曾用 200 MHz 常量算 190 MHz"
    L1136   "200 MHz WNS −0.104 ns（当时频点）"

An unmarked mention is the fault. This check finds one by requiring, on the same line, a
historical marker OR an explicit contrast with 190 MHz.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Markers that make a 200 MHz mention obviously historical.
MARKERS = re.compile(
    r"早期|此前|曾写|曾用|曾经|当时|该构建|旧构建|history|historical|superseded")

print("every mention of 200 MHz, and whether it is marked")
print()

fails = []
total = 0
for m in re.finditer(r"[^\n]*\b200(?:\.\d+)?\s*MHz[^\n]*", text):
    total += 1
    ln = text[:m.start()].count("\n") + 1
    line = m.group(0)
    marked = bool(MARKERS.search(line))
    contrasts = bool(re.search(r"190\s*MHz", line))
    ok = marked or contrasts
    if not ok:
        fails.append((ln, line.strip()[:90]))
    print("  L%-5d %-5s %s" % (ln, "ok" if ok else "UNMARKED", line.strip()[:78]))

print()
print("  mentions: %d, unmarked: %d" % (total, len(fails)))

# The shipped frequency must appear, and more often than the historical one.
shipped = text.count("190 MHz")
print("  190 MHz mentions: %d" % shipped)
if shipped == 0:
    fails.append((0, "the shipped 190 MHz is not mentioned at all"))

print()
if fails:
    print("CLOCK-MARKING-FAIL (%d)" % len(fails))
    for ln, line in fails:
        print("  L%d: %s" % (ln, line))
    sys.exit(1)
print("CLOCK-MARKING-PASS (200 MHz is always marked historical; 190 MHz is stated)")
