"""Confirm check_sim_kinds catches a mis-declared suite.

Three mutations, each expected to fail the check:

  1. remove the kind from an entry        -> "kind missing"
  2. declare KIND_PASS on coldstart       -> a FAIL token declared as a pass
  3. declare KIND_EXPECTED on a PASS entry-> the expected-failure rule misapplied

Mutation 2 is the one that matters: it would re-open the exact fragility round 28
fixed, letting an expected failure be treated like a broken suite.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

PATH = r"D:\agent\nasdaq-fpga\tools\run_sims.py"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_sim_kinds.py"

original = io.open(PATH, encoding="utf-8").read()
backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(PATH, backup)

MUTATIONS = [
    ("drop a kind", lambda s: s.replace(
        '"TS-HIST-ALL-PASS", False, KIND_PASS),',
        '"TS-HIST-ALL-PASS", False),', 1)),
    ("coldstart -> KIND_PASS", lambda s: s.replace(
        '"COLD-FAIL", True, KIND_EXPECTED),',
        '"COLD-FAIL", True, KIND_PASS),', 1)),
    ("stream -> KIND_EXPECTED", lambda s: s.replace(
        '"STREAM-PASS", True, KIND_PASS),',
        '"STREAM-PASS", True, KIND_EXPECTED),', 1)),
]

results = []
for name, fn in MUTATIONS:
    mutated = fn(original)
    landed = mutated != original
    io.open(PATH, "w", encoding="utf-8", newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
    caught = (r.returncode != 0)
    results.append((name, landed, caught))
    print("%-26s landed=%-5s check exit=%d  %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(PATH, "w", encoding="utf-8", newline="\n").write(original)

restored = io.open(PATH, encoding="utf-8").read() == original
print("restored: %s" % restored)

# Healthy file must pass.
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

print()
if all(landed and caught for _, landed, caught in results) and restored \
        and r.returncode == 0:
    print("KIND-MUTATION-PASS")
else:
    print("KIND-MUTATION-FAIL")
    sys.exit(1)
