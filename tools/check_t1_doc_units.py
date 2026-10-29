"""Does the documentation attach TIME units to quantities the RTL measures in CYCLES?

`check_t1_units` compares the RTL's bucket shift with the driver's constant. It reads neither the report nor the
defect log. Round 21's error lived entirely in the report:

    | 直方图覆盖 | 0-2040 ns（256 x 8 ns 桶） |

The RTL makes a bucket 8 CYCLES (`delta64_r[HIST_BIN_W+2:3]`). "8 ns" and "2040 ns" were both wrong by the clock
period, 5.26x.

This closes that seam: any prose statement of a per-bucket width or coverage must not use a bare time unit.
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

m = re.search(r"delta64_r\[HIST_BIN_W\+2:(\d+)\]", rtl)
if not m:
    print("T1-DOC-UNITS-FAIL: cannot find the bucket shift in ts_hist.v")
    sys.exit(1)
LSB = int(m.group(1))
BINS = int(re.search(r"parameter HIST_BINS\s*=\s*(\d+)", rtl).group(1))
STEP_CYCLES = 1 << LSB
STEP_NS = STEP_CYCLES * 1e9 / 190e6
SPAN_NS = BINS * STEP_NS

print("RTL: bucket = %d cycles = %.4f ns;  %d buckets span %.1f ns"
      % (STEP_CYCLES, STEP_NS, BINS, SPAN_NS))
print()

# A per-bucket width stated as a bare time unit. "8 周期" and "8 cycles" are fine; "8 ns" is not.
BAD_WIDTH = re.findall(r"(?<![\d.])(\d)\s*ns\s*桶|每桶\s*(\d)\s*ns(?![a-zA-Z])|bucket\s*\d+\s*ns", text)
# A coverage figure that disagrees with the RTL by the clock period.
BAD_SPAN = []
for m2 in re.finditer(r"0\s*[–\-]\s*([\d,]+)\s*ns", text):
    val = float(m2.group(1).replace(",", ""))
    if 0 < val < 100000 and abs(val - SPAN_NS) > 1.0 and abs(val - SPAN_NS / 5.263157) < 2.0:
        BAD_SPAN.append((val, m2.start()))

fails = []
if BAD_WIDTH:
    print("  per-bucket width stated in a time unit: %d hit(s)" % len(BAD_WIDTH))
    fails.append("bucket width stated as a time unit")
else:
    print("  per-bucket width             : states cycles, not a time unit")

if BAD_SPAN:
    for val, _ in BAD_SPAN:
        print("  coverage %s ns is %.2fx the real %.1f ns - exactly the clock-period factor"
              % (val, SPAN_NS / val, SPAN_NS))
    fails.append("coverage stated with the clock-period error")
else:
    print("  coverage                     : %.1f ns, consistent with the RTL" % SPAN_NS)

# The stated coverage must actually appear.
if ("10,779" not in text) and ("10779" not in text) and ("10778.9" not in text):
    print("  the report never states the computed coverage %.1f ns" % SPAN_NS)
    fails.append("coverage not stated")

print()
if fails:
    print("T1-DOC-UNITS-FAIL (%s)" % ", ".join(fails))
    sys.exit(1)

print("T1-DOC-UNITS-PASS (per-bucket width is in cycles and the coverage matches the RTL)")
