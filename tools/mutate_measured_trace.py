"""Mutations for the measured-trace check.

  1. put 615 MB/s back on a 实测 line      -> no board record, must FAIL
  2. change a recorded latency (210.5)     -> the record does not contain it
  3. mark the whole report's claims as absent by emptying the evidence -> must FAIL
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_measured_trace.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=REPORT, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

MUTATIONS = []

# 1. reintroduce the invented measurement (round 3: anchor updated to the current wording)
m1 = original.replace(
    "缺口来自驱动与描述符开销（见 §11.4 的分块扫描）。",
    "缺口来自驱动与描述符开销。**板上实测的 DMA 速率为 615 MB/s**。",
    1)
if m1 == original:
    # The sentence has been rewritten since; append an unambiguous claim instead.
    m1 = original + "\n**板上实测的 DMA 速率为 615 MB/s**。\n"
if m1 != original:
    MUTATIONS.append(("reintroduce 615 MB/s", m1))

# 2. alter a recorded latency
m2 = original.replace("210.5", "212.7")
if m2 != original:
    MUTATIONS.append(("alter P50 210.5 -> 212.7", m2))

# 3. corrupt every latency figure at once (the whole T1 set)
m3 = original.replace("210.5", "999.1").replace("1052.6", "999.2").replace("1136.8", "999.3")
if m3 != original:
    MUTATIONS.append(("alter the whole T1 set", m3))

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-28s landed=%-5s exit=%d %s"
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
if results and all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("MEASURED-TRACE-MUTATION-PASS")
else:
    print("MEASURED-TRACE-MUTATION-FAIL")
    sys.exit(1)
