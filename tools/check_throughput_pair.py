"""Require the board throughput to appear alongside the simulated one.

The report carries two throughput figures for the same design:

    3,344,390 msg/s   simulation - PL cycle count, 299.01 ns/message
    2,230,335 msg/s   board - through the real driver and AXI DMA

Both are true. They differ by 33% because the simulation window starts at the first
accepted byte and ends at the last emitted event, inside the PL, while the board run
also pays DMA descriptor setup, DDR read latency, driver polling and loop overhead.

Before round 46 the board figure appeared ONCE, inside the provenance note, while the
simulated one appeared in the top summary, section 11.1 and section 11.2. A reader who
read the summary and stopped would conclude the design runs at 3.34 M msg/s with no
indication that the board says otherwise.

That is a selective-presentation fault, and it is the kind that survives editing because
each individual sentence is true.

This check requires:
  * both figures present;
  * the board figure present in the summary block at the top;
  * the ratio stated, so a reader does not have to compute it.
"""
import io
import os
import re
import sys

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(REPORT):
    print("THROUGHPUT-PAIR-FAIL (no report)")
    sys.exit(1)

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
lines = text.split("\n")

SIM = "3,344,390"
BRD = "2,230,335"

print("throughput figures in the report")
print()
print("  simulation figure present : %s" % (SIM in text))
print("  board figure present      : %s" % (BRD in text))

# The top summary is the blockquote near the start (first ~60 lines).
head = "\n".join(lines[:60])
in_summary = BRD in head
print("  board figure in summary   : %s" % in_summary)

# Ratio stated?
has_ratio = bool(re.search(r"66\.7", text))
print("  ratio stated              : %s" % has_ratio)

# Count mentions as a sanity signal.
print()
print("  occurrences: simulation %d, board %d"
      % (text.count(SIM), text.count(BRD)))

fails = []
if SIM not in text:
    fails.append("the simulated throughput figure is missing")
if BRD not in text:
    fails.append("the board throughput figure is missing")
if not in_summary:
    fails.append("the board figure is absent from the top summary - a reader who "
                 "stops there sees only the simulated number")
if not has_ratio:
    fails.append("the 66.7% ratio is not stated, so the gap between the two is "
                 "left for the reader to notice")
if text.count(BRD) < 2:
    fails.append("the board figure appears only once, which means it is not "
                 "reachable from the performance sections")

print()
if fails:
    print("THROUGHPUT-PAIR-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("THROUGHPUT-PAIR-PASS (both figures, side by side, with the gap explained)")
