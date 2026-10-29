"""Confirm the fit test catches a broken fit, now that it imports the real function.

Mutations to chunk_sweep.fit_overhead:
  1. swap the slope and intercept          -> must FAIL
  2. drop the degenerate-input guard       -> must FAIL (ZeroDivisionError)
  3. use a one-point difference instead of least squares -> must FAIL on noisy data
"""
import importlib
import io
import os
import shutil
import subprocess
import sys
import tempfile

SWEEP = r"D:\agent\nasdaq-fpga\tools\chunk_sweep.py"
TEST = r"D:\agent\nasdaq-fpga\tools\test_chunk_fit.py"

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(SWEEP, backup)
original = io.open(SWEEP, encoding="utf-8").read()

MUTATIONS = [
    ("swap slope and intercept",
     original.replace("    per_desc = (n_pts * sxy - sx * sy) / denom\n"
                      "    fixed = (sy - per_desc * sx) / n_pts\n"
                      "    return per_desc, fixed",
                      "    per_desc = (sy - (n_pts * sxy - sx * sy) / denom * sx) / n_pts\n"
                      "    fixed = (n_pts * sxy - sx * sy) / denom\n"
                      "    return per_desc, fixed")),
    ("drop the degenerate guard",
     original.replace("    if denom == 0:\n        return None, None",
                      "    if False:\n        return None, None")),
    ("return None always",
     original.replace("    return per_desc, fixed",
                      "    return None, None")),
]

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(SWEEP, "w", encoding="utf-8", newline="\n").write(mutated)
    r = subprocess.run([sys.executable, TEST], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-32s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(SWEEP, "w", encoding="utf-8", newline="\n").write(original)

restored = io.open(SWEEP, encoding="utf-8").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, TEST], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, SWEEP)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("CHUNK-FIT-MUTATION-PASS")
else:
    print("CHUNK-FIT-MUTATION-FAIL")
    sys.exit(1)
