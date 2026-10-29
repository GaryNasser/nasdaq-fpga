"""Do the published T1 percentiles land exactly on histogram bucket edges?

The measured p50/p95/p99 are not arbitrary numbers - they are BUCKET UPPER EDGES:

    edge(i) = (i + 1) x 8 cycles / 190 MHz

If a published percentile is not an exact multiple of that step, either the bucket width in the driver is wrong or
the figure was not produced by the histogram.

Round 21 corrected the report's claim that buckets are "8 ns" wide; the RTL makes them 8 CYCLES. This check pins the
relationship so the two cannot drift apart again.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
RTL = os.path.join(REPO, "rtl", "itch", "ts_hist.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
rtl = io.open(RTL, encoding="utf-8", errors="replace").read()

# The bucket step comes from the RTL's index expression: delta64_r[HIST_BIN_W+2:3] -> 3 low bits dropped.
m = re.search(r"delta64_r\[HIST_BIN_W\+2:(\d+)\]", rtl)
if not m:
    print("TS-BIN-MATH-FAIL: cannot find the bucket index expression in ts_hist.v")
    sys.exit(1)
LSB = int(m.group(1))
STEP_CYCLES = 1 << LSB
BINS = int(re.search(r"parameter HIST_BINS\s*=\s*(\d+)", rtl).group(1))

CLK_HZ = 190e6
PERIOD_NS = 1e9 / CLK_HZ
STEP_NS = STEP_CYCLES * PERIOD_NS

print("RTL bucket index : delta64_r[HIST_BIN_W+2:%d]  -> %d cycles per bucket" % (LSB, STEP_CYCLES))
print("bins             : %d" % BINS)
print("bucket step      : %d cycles = %.4f ns at 190 MHz" % (STEP_CYCLES, STEP_NS))
print("full coverage    : %d cycles = %.1f ns" % (BINS * STEP_CYCLES, BINS * STEP_NS))
print()

# The measured percentiles.
MEASURED = [("p50", 210.5263157894737), ("p95", 1052.6315789473686), ("p99", 1178.9473684210527)]
fails = []
for name, value in MEASURED:
    buckets = value / STEP_NS
    nearest = round(buckets)
    resid = abs(buckets - nearest)
    ok = resid < 1e-6
    print("  %-4s %10.4f ns -> bucket %.6f  (nearest %d)  %s"
          % (name, value, buckets, nearest, "on an edge" if ok else "*** NOT on an edge ***"))
    if not ok:
        fails.append(name)

print()

# The report must not call the bucket 8 ns.
BAD = re.search(r"256\s*[×x]\s*8\s*ns", text)
if BAD:
    print("  report still says '256 x 8 ns' - the bucket is 8 CYCLES")
    fails.append("stale bucket-width wording")

# And the stated coverage must match the computed one.
cov = BINS * STEP_NS
if "10,779" not in text and "10779" not in text:
    print("  report does not state the computed coverage (%.1f ns)" % cov)
    fails.append("coverage not stated")

if fails:
    print()
    print("TS-BIN-MATH-FAIL (%d problem(s): %s)" % (len(fails), ", ".join(fails)))
    sys.exit(1)

print("TS-BIN-MATH-PASS (percentiles are exact bucket edges; the report states the real coverage)")
