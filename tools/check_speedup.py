"""Recompute the speedup and its uncertainty from the recorded measurements.

The 3.10x headline came from best-of-4 A9 runs against a cycle-counted PL figure.
Both sides have different statistical character, and neither was ever combined
with its uncertainty:

    PL  : cycle-counted -> exactly reproducible, zero variance
    A9  : wall clock on a board -> 927.35 to 1414.30 ns/msg across four runs

This script recomputes the ratio and reports the range over the defensible
choices, so the published number can be checked and its sensitivity seen. It does
not need the board - it reads docs/measurements/baseline-a9.txt and the PL
constants below, and fails if the published speedup is not inside the range it
derives.
"""
import io
import re
import sys

BASELINE = r"D:\agent\nasdaq-fpga\docs\measurements\baseline-a9.txt"

# PL side: cycle-counted, identical on every run (verified by re-running).
PL_CYC_PER_MSG = 56.813
PL_CLK_MHZ = 190.0
PL_NS = PL_CYC_PER_MSG * (1000.0 / PL_CLK_MHZ)

text = io.open(BASELINE, encoding="utf-8", errors="replace").read()

# Single-stock runs only (43428 messages).
single = [float(m) for m in
          re.findall(r"msgs=43428\s+bytes=\d+\s+elapsed_ns=\d+\s+ns_per_msg=([\d.]+)",
                     text)]
if not single:
    print("no single-stock runs found in the baseline file")
    sys.exit(1)

print("A9 single-stock runs (ns/msg): %s" % ", ".join("%.2f" % v for v in single))
print("PL side: %d cycles/msg at %g MHz = %.2f ns/msg (cycle-counted, zero variance)"
      % (PL_CYC_PER_MSG, PL_CLK_MHZ, PL_NS))
print()

warm = single[1:] if len(single) > 1 else single
scenarios = [
    ("best warm (the published basis)", min(warm)),
    ("mean of warm runs", sum(warm) / len(warm)),
    ("median of all runs", sorted(single)[len(single) // 2]),
    ("mean of all runs", sum(single) / len(single)),
    ("worst (cold cache)", max(single)),
]

print("speedup sensitivity:")
lo = None
hi = None
for label, base in scenarios:
    sp = base / PL_NS
    print("  %-32s %8.2f ns  -> %5.2fx" % (label, base, sp))
    lo = sp if lo is None else min(lo, sp)
    hi = sp if hi is None else max(hi, sp)

published = 3.10
print()
print("defensible range: %.2fx .. %.2fx" % (lo, hi))

fails = []
# The published figure must be the conservative (lowest) defensible end.
best_warm = min(warm) / PL_NS
if abs(best_warm - published) > 0.05:
    fails.append("published %.2fx != best-warm %.2fx" % (published, best_warm))
# And it must be inside the full range.
if not (lo - 0.05 <= published <= hi + 0.05):
    fails.append("published %.2fx outside range %.2fx..%.2fx" % (published, lo, hi))

print()
if fails:
    print("SPEEDUP-AUDIT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("published 3.10x is the conservative end of the defensible range")
print("SPEEDUP-AUDIT-PASS")
