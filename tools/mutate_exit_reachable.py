"""Confirm check_exit_reachable catches a checker that cannot fail.

Mutation: strip the sys.exit from a checker that prints FAIL, reproducing check_golden's
defect exactly.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TARGET = r"D:\agent\nasdaq-fpga\tools\check_golden.py"
SCAN = r"D:\agent\nasdaq-fpga\tools\check_exit_reachable.py"

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(TARGET, backup)
original = io.open(TARGET, encoding="utf-8").read()

mutated = original.replace(
    "    # Exit non-zero: without this the runner records PASS for a check that printed FAIL.\n"
    "    sys.exit(1)\n", "", 1)
landed = mutated != original
io.open(TARGET, "w", encoding="utf-8", newline="\n").write(mutated)

r = subprocess.run([sys.executable, SCAN], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
out = (r.stdout or "") + (r.stderr or "")
caught = r.returncode != 0 and "check_golden.py" in out

print("mutation landed        : %s" % landed)
print("scan exit code         : %d" % r.returncode)
print("check_golden named     : %s" % ("check_golden.py" in out))
print("=> caught              : %s" % caught)

shutil.copyfile(backup, TARGET)
os.unlink(backup)
restored = io.open(TARGET, encoding="utf-8").read() == original
print("restored               : %s" % restored)

r2 = subprocess.run([sys.executable, SCAN], capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
print("healthy scan exit      : %d" % r2.returncode)

print()
if landed and caught and restored and r2.returncode == 0:
    print("EXIT-REACHABLE-MUTATION-PASS")
else:
    print("EXIT-REACHABLE-MUTATION-FAIL")
    sys.exit(1)
