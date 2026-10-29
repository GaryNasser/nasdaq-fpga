"""Confirm check_codec_explicit catches a newly-added implicit codec.

The regression to guard against is a new `subprocess.run(..., text=True, encoding="utf-8", errors="replace")` written
without an encoding - the exact shape that produced round 42's environment-dependent
verdict.

Two mutations:
  1. strip encoding= from a checker's subprocess call -> must FAIL
  2. strip encoding= from an audit_*.py it depends on -> must FAIL (transitive)
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
CHECK = os.path.join(TOOLS, "check_codec_explicit.py")

results = []

for target, label in (("check_tool_claims.py", "direct checker"),
                      ("audit_deliverables.py", "transitive dependency")):
    path = os.path.join(TOOLS, target)
    backup = tempfile.mktemp(suffix=".py")
    shutil.copyfile(path, backup)
    original = io.open(path, encoding="utf-8").read()

    # Remove the codec arguments from the first call that has them.
    mutated = re.sub(r'text=True, encoding="utf-8", errors="replace"',
                     "text=True", original, count=1)
    if mutated == original:
        # try io.open form
        mutated = re.sub(r', encoding="utf-8", errors="replace"\)', ")", original, count=1)
    landed = mutated != original

    io.open(path, "w", encoding="utf-8", newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((label, landed, caught))
    print("%-24s landed=%-5s exit=%d %s"
          % (label, landed, r.returncode, "CAUGHT" if caught else "MISSED"))

    shutil.copyfile(backup, path)
    os.unlink(backup)

restored = True
for target in ("check_tool_claims.py", "audit_deliverables.py"):
    pass
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

print()
if all(l and c for _, l, c in results) and r.returncode == 0:
    print("CODEC-EXPLICIT-MUTATION-PASS")
else:
    print("CODEC-EXPLICIT-MUTATION-FAIL")
    sys.exit(1)
