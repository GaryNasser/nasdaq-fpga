"""Confirm check_busyrun_direction catches a contradiction.

Two mutations:
  1. swap the figures so busy_run < T1  -> the measurements contradict
  2. make them wildly different (busy 2000) -> no longer comparable intervals
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_busyrun_direction.py"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=REPORT, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

MUTATIONS = [
    ("swap the figures",
     original.replace("`max_busy_run`(775) > T1 `max`(735)",
                      "`max_busy_run`(600) > T1 `max`(735)", 1)
     .replace("`max_busy_run=775`", "`max_busy_run=600`", 1)),
    ("not comparable",
     original.replace("`max_busy_run=775`", "`max_busy_run=2000`", 1)
     .replace("`max_busy_run`(775)", "`max_busy_run`(2000)", 1)
     .replace("`max_busy_run`(2000) > T1", "`max_busy_run`(2000) > T1", 1)),
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
    print("%-22s landed=%-5s exit=%d %s"
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
    print("BUSYRUN-MUTATION-PASS")
else:
    print("BUSYRUN-MUTATION-FAIL")
    sys.exit(1)
