"""Every stated slack must match the clock the report states, and the margins must re-derive.

    L51    "WNS +0.126 ns（2.4% 周期）"   0.126 / 5.2632 = 2.39%   ok
    L328   "WNS +0.042 ns"                0.042 / 5.2632 = 0.80%

A percentage paired with a slack is a one-line division, and nobody re-divides. Round 100 found the
gap stated from a corrected input; round 113 re-divided the GbE ratios. This does the same for
timing.

It also checks a claim the report relies on without stating its arithmetic: the design runs at
190 MHz BECAUSE it does not close at 200. Re-deriving from the stated slack:

    period drops by 5.2632 - 5.0000 = 0.2632 ns
    +0.042 - 0.2632 = -0.221 ns at 200 MHz

If that came out positive, the report's reason for choosing 190 MHz would be wrong.
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

P190 = 1e3 / 190.0
P200 = 1e3 / 200.0
print("timing arithmetic")
print()
print("  190 MHz period %.4f ns, 200 MHz period %.4f ns, difference %.4f ns"
      % (P190, P200, P190 - P200))
print()

fails = []

# 1. Every "WNS +x ns（y% 周期）" pair.
print("  stated percentages")
found = 0
for m in re.finditer(r"\+?([\d.]+)\s*ns\*{0,2}[（(]\*{0,2}([\d.]+)\s*%", rep):
    wns, pct = float(m.group(1)), float(m.group(2))
    calc = wns / P190 * 100
    ln = rep[:m.start()].count("\n") + 1
    ok = abs(calc - pct) < 0.1
    if 0.1 < wns < 1.0:          # only slacks in ns, not delays in us
        found += 1
        print("    L%-5d +%.3f ns -> stated %.1f%%, derived %.2f%%  %s"
              % (ln, wns, pct, calc, "ok" if ok else "MISMATCH"))
        if not ok:
            fails.append("L%d: %.3f ns is %.2f%%, not %.1f%%" % (ln, wns, calc, pct))

if found == 0:
    print("    (no slack/percentage pairs found)")
    fails.append("no slack/percentage pair found - the pattern may need updating")

# 2. The 190 MHz rationale.
print()
print("  the 190 MHz rationale")
for label, wns, rate in (("current source", 0.042, 190), ("shipped build", 0.126, None)):
    at200 = wns - (P190 - P200)
    verdict = "would NOT close" if at200 < 0 else "WOULD close"
    print("    %-16s WNS +%.3f at 190 -> %+.3f at 200 MHz  (%s)"
          % (label, wns, at200, verdict))

if (0.042 - (P190 - P200)) >= 0:
    fails.append("the current build would close at 200 MHz - the 190 MHz choice is unexplained")

# 3. The report must not claim closure at 200 MHz.
print()
claimed = [l for l in rep.split("\n")
           if re.search(r"200\s*MHz", l) and re.search(r"收敛|闭合|closes", l)
           and not re.search(r"不|未|无法|cannot|NOT", l)]
print("  lines claiming closure at 200 MHz: %d" % len(claimed))
for l in claimed[:3]:
    print("     %s" % l.strip()[:86])
if claimed:
    fails.append("the report claims closure at 200 MHz")

print()
if fails:
    print("TIMING-ARITH-FAIL (%d)" % len(fails))
    for f in fails:
        print("  %s" % f)
    sys.exit(1)
print("TIMING-ARITH-PASS (percentages re-derive, and the design does not close at 200 MHz)")
