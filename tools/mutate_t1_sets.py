"""Confirm check_t1_sets catches the two T1 populations being conflated.

Mutations:
  1. collapse the sample counts to one value   -> must FAIL
  2. make both p99 the same                    -> must FAIL
  3. delete the simulated p99                  -> must FAIL
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_t1_sets.py"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=REPORT, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

MUTATIONS = [
    ("collapse sample counts",
     original.replace("19,969", "19961")),
    ("same p99",
     original.replace("1,178.9", "1136.8")),
    ("delete simulated p99",
     original.replace("1,178.9", "N/A")),
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
    print("%-24s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(original)

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
    print("T1-SETS-MUTATION-PASS")
else:
    print("T1-SETS-MUTATION-FAIL")
    sys.exit(1)
