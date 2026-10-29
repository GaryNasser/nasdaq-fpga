"""Extend the margin check: setup and hold must be separately labelled in the table.

Round 52 found the module table comparing setup and hold values in one "worst" column:

    mold64_reasm   +0.042   (setup)
    order_book     +0.034   (hold)

Two different quantities ranked together. A reader would conclude order_book has the
tightest setup path, when it has no setup path in the list at all - all four of its tight
paths are hold.

I introduced that error myself, then also fabricated a +0.036 setup value for order_book
by inference rather than reading the Path Type line. Both are fixed, and the check should
now prevent the recurrence.

Added assertions:
  * the table has separate 建立 / 保持 columns;
  * it states that the two are not comparable;
  * it does not assign a setup value to a module whose tight paths are all hold.
"""
import io
import os
import re
import sys

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(REPORT):
    print("MARGIN-DISCLOSURE-FAIL (no report)")
    sys.exit(1)

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

start = text.find("### 4.1b")
if start == -1:
    print("MARGIN-DISCLOSURE-FAIL (1)")
    print("  no subsection states the timing margin in context")
    sys.exit(1)

nxt = re.search(r"\n#{2,3} ", text[start + 10:])
end = start + 10 + nxt.start() if nxt else len(text)
section = text[start:end]

# The margins themselves are read from the routed report, and the two ratios are derived
# from them, because the hardcoded pair went stale the moment the build changed: the check
# still demanded the WNS +0.042 / WHS +0.034 of round 52 while the shipped build had
# +0.094 / +0.012, so a correct section failed and the numbers that matter most - how thin
# the margin is - were pinned to a build that is no longer on the board.
IMP = r"D:\agent\nasdaq-fpga\vivado\workspace\nasdaq\nasdaq.runs\impl_1"
VAR = 0.031          # documented rebuild variance: round 30, same source, same machine
ts = io.open(os.path.join(IMP, "nasdaq_wrapper_timing_summary_routed.rpt"),
             encoding="utf-8", errors="replace").read()
mt = re.search(r"^\s+(-?\d+\.\d+)\s+-?\d+\.\d+\s+\d+\s+\d+\s+(-?\d+\.\d+)", ts, re.M)
if not mt:
    print("MARGIN-DISCLOSURE-FAIL (1)")
    print("  cannot read WNS/WHS out of the routed timing summary")
    sys.exit(1)
WNS, WHS = float(mt.group(1)), float(mt.group(2))
setup_ratio = int(round(100.0 * VAR / WNS))
hold_ratio = int(round(100.0 * VAR / WHS))

print("timing-margin disclosure, section 4.1b (%d chars)" % len(section))
print("  build under discussion: WNS %.3f, WHS %.3f, variance %.3f"
      % (WNS, WHS, VAR))
print("  ratios this build requires: setup %d %%, hold %d %%"
      % (setup_ratio, hold_ratio))
print()

fails = []

CHECKS = [
    ("setup margin %.3f" % WNS, r"\+%s\s*ns" % re.escape("%.3f" % WNS),
     "the current-source setup margin is not cited"),
    ("hold margin WHS %.3f" % WHS, r"WHS[^\n]{0,12}?%s" % re.escape("%.3f" % WHS),
     "the hold margin (WHS %.3f) is not cited - it is the tighter of the two" % WHS),
    ("rebuild variance 0.031", r"0\.031\s*ns",
     "the rebuild variance is not cited"),
    ("setup ratio %d%%" % setup_ratio, r"%d\s*%%" % setup_ratio,
     "the setup ratio is not stated"),
    ("hold ratio %d%%" % hold_ratio, r"%d\s*%%" % hold_ratio,
     "the hold ratio is not stated; without it the setup figure flatters the design"),
    ("hold is unrecoverable", r"保持违例不能|不可恢复",
     "the report does not say hold violations cannot be recovered by clocking"),
    ("tight path count 30", r"30\s*条", "the number of tight paths is not stated"),
    ("path total 80", r"80\s*条", "the denominator for '30' is not stated"),
    ("Xilinx IP limitation", r"axi_mem_intercon",
     "the path breakdown does not identify how many tight paths are inside IP"),
    # New this round.
    ("setup/hold columns separate", r"最差建立.*最差保持",
     "the module table does not separate setup from hold margins"),
    ("table says they are incomparable", r"不能互相比较|同一把尺子",
     "the table does not state that setup and hold margins are not comparable"),
    ("hold-only modules marked", r"只有保持路径|全部是保持",
     "the table does not mark which modules have only hold paths"),
]

for label, pat, why in CHECKS:
    ok = bool(re.search(pat, section))
    print("  %-32s : %s" % (label, ok))
    if not ok:
        fails.append(why)

# order_book must not be given a setup figure: all its tight paths are hold.
m = re.search(r"\|\s*`order_book`\s*\|[^\n]*\|", section)
if m:
    row = m.group(0)
    invents_setup = bool(re.search(r"\+\d\.\d+", row.split("|")[3]))
    print("  %-32s : %s" % ("order_book row invents setup", invents_setup))
    if invents_setup:
        fails.append("the order_book row carries a setup value, but all four of its "
                     "tight paths are hold")

bad = re.search(r"是手写 RTL 路径换来的", text)
print("  %-32s : %s" % ("claims margin as achievement", bool(bad)))
if bad:
    fails.append("the report credits hand-written RTL for the timing margin")

print()
if fails:
    print("MARGIN-DISCLOSURE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("MARGIN-DISCLOSURE-PASS")
