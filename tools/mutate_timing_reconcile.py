"""Mutation test for the timing reconciler, with values that are genuinely untraceable.

The first version used 0.036 as a "fabricated" value. It is not fabricated - it is a real
hold slack (order_book/map_addr_reg[11]/D). The checker accepted it correctly, and the
test was wrong.

It also edited the section 4.1 table, which lies OUTSIDE section 4.1b, so the reconciler
never saw the change. Scope, not truth.

This version:
  * uses values verified absent from the routed report (0.037, 0.048, 0.049);
  * applies them inside section 4.1b;
  * also tests the derived-average and mis-rounding paths.

Candidates were picked programmatically from the report's slack list, so the test cannot
drift into using a true value again.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_timing_reconcile.py"
RPT = (r"D:\agent\nasdaq-fpga\vivado\workspace\nasdaq\nasdaq.runs\impl_1"
       r"\nasdaq_wrapper_timing_summary_routed.rpt")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Verify the chosen values really are absent from the measurement.
rpt = io.open(RPT, encoding="utf-8", errors="replace").read()
measured = set(round(float(v), 3) for v in
               re.findall(r"Slack \((?:MET|VIOLATED)\)\s*:\s*([-+]?\d+\.\d+)ns", rpt))
FABRICATED = [0.037, 0.048, 0.049]
assert not any(v in measured for v in FABRICATED), \
    "a chosen mutation value is a real measurement"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# All edits target a row inside section 4.1b.
ROW = "| `mold64_reasm` | 10 | +0.042 ns"
assert ROW in original, "anchor row not found in the report"

MUTATIONS = [
    ("fabricate 0.037 setup",
     original.replace(ROW, "| `mold64_reasm` | 10 | +0.037 ns", 1)),
    ("fabricate 0.049 setup",
     original.replace(ROW, "| `mold64_reasm` | 10 | +0.049 ns", 1)),
    ("alter the derived average",
     original.replace("| 4.712 ns |", "| 4.900 ns |", 1)),
    ("misround 3.407 as 3.9",
     original.replace("3.4 ns 走线", "3.9 ns 走线", 1)),
]

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-30s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(original)
    sys.stdout.flush()

restored = io.open(REPORT, encoding="utf-8",
                   errors="surrogateescape").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, REPORT)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("TIMING-RECONCILE-MUTATION-PASS")
else:
    print("TIMING-RECONCILE-MUTATION-FAIL")
    sys.exit(1)
