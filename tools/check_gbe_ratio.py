"""Every "Nx 1 GbE" ratio re-derived from the MB/s figure it accompanies.

    stated 1.52x   190.0 / 125 = 1.52   ok
    stated 0.50x    63.0 / 125 = 0.50   ok
    stated 0.76x    94.5 / 125 = 0.76   ok

125 MB/s is 1 GbE's line rate (1e9 bits/s / 8), the conventional denominator. The three figures
are the design's ceiling, its measured rate, and its simulated pipeline rate.

Each is a one-line division, which is exactly why a stale one can survive: nobody re-divides.
Round 100 found the gap stated as 32.9% from a corrected input; this asks whether any ratio has
the same problem.
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
LINE = 125.0   # 1 GbE in MB/s

print("every MB/s figure paired with an 'Nx 1 GbE' ratio")
print()

pairs = re.findall(r"(\d+\.?\d*)\s*MB/s（\*{0,2}([\d.]+)×\s*1\s*GbE", rep)
if not pairs:
    print("  no ratio pairs found - the pattern needs updating or the claims are gone")
    sys.exit(1)

fails = []
seen = set()
for mb, ratio in pairs:
    key = (float(mb), float(ratio))
    if key in seen:
        continue
    seen.add(key)
    calc = float(mb) / LINE
    ok = abs(calc - float(ratio)) < 0.02
    print("  %7.1f MB/s  stated %.2fx  derived %.2fx  %s"
          % (float(mb), float(ratio), calc, "ok" if ok else "MISMATCH"))
    if not ok:
        fails.append("%s MB/s != %.2fx" % (mb, float(ratio)))

print()
print("  distinct pairs: %d" % len(seen))

if fails:
    print()
    print("GBE-RATIO-FAIL (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print()
print("GBE-RATIO-PASS (every ratio re-derives from the figure it qualifies)")
