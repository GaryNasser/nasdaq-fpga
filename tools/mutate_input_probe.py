"""Confirm the probe test catches a broken precondition check.

A precondition that always passes is worse than none: it reports "board ready" and then
the golden run fails opaquely. So the test must fail if the probe stops distinguishing.

Mutations:
  1. remove the isdigit guard (always proceed)   -> must FAIL
  2. remove the size comparison                  -> must FAIL
  3. return the wrong code on mismatch           -> must FAIL
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

RECOVER = r"D:\agent\nasdaq-fpga\tools\board_recover.py"
TEST = r"D:\agent\nasdaq-fpga\tools\test_input_probe.py"

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(RECOVER, backup)
original = io.open(RECOVER, encoding="utf-8").read()

MUTATIONS = [
    ("always proceed",
     original.replace("    if not rr.stdout.strip().isdigit():",
                      "    if False:", 1)),
    ("ignore the size",
     original.replace("    if remote_size != expected:", "    if False:", 1)),
    ("wrong exit code on mismatch",
     original.replace("        print('  the driver enforces this via REFERENCE_CAPTURE_SIZE"
                      " and would return 6')\n        return 5",
                      "        print('  the driver enforces this via REFERENCE_CAPTURE_SIZE"
                      " and would return 6')\n        return 0", 1)),
]

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(RECOVER, "w", encoding="utf-8", newline="\n").write(mutated)
    r = subprocess.run([sys.executable, TEST], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-30s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(RECOVER, "w", encoding="utf-8", newline="\n").write(original)

restored = io.open(RECOVER, encoding="utf-8").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, TEST], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, RECOVER)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("INPUT-PROBE-MUTATION-PASS")
else:
    print("INPUT-PROBE-MUTATION-FAIL")
    sys.exit(1)
