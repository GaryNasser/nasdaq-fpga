"""Mutate tb_parity2 back to an unguarded PASS token and confirm detection.

Before round 21 tb_parity2 printed PARITY-TOTAL unconditionally and never failed.
Round 21 added:

    if (parity_errs == 0 && first_bad < 0 ... ) $display("PARITY-PASS");
    else                                       $display("PARITY-FAIL");

check_suite_asserts.py must notice if the PASS token becomes unconditional again.
This replaces the guarded display with a bare one, verifies the mutation landed, and
runs the check.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TB = r"D:\agent\nasdaq-fpga\tools\tb_parity2.v"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_suite_asserts.py"

backup = tempfile.mktemp(suffix=".v")
shutil.copyfile(TB, backup)

src = io.open(TB, encoding="utf-8").read()

# Remove the guard line so the PARITY-PASS display becomes unconditional.
guard = "if (parity_errs == 0 && first_bad < 0"
i = src.find(guard)
assert i != -1, "guard not found"
line_start = src.rfind("\n", 0, i) + 1
line_end = src.find("\n", src.find("dut.error_count == 0)", i))
assert line_end != -1, "end of guard not found"

mutated = src[:line_start] + src[line_end + 1:]

io.open(TB, "w", encoding="utf-8", newline="\n").write(mutated)

after = io.open(TB, encoding="utf-8").read()
landed = guard not in after and "PARITY-PASS" in after
print("mutation landed: %s" % landed)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("check exit code: %d" % r.returncode)
for line in (r.stdout or "").strip().splitlines()[-3:]:
    print("  " + line)

shutil.copyfile(backup, TB)
os.unlink(backup)

print()
if not landed:
    print("MUTATION-DID-NOT-APPLY")
    sys.exit(2)
if r.returncode == 0:
    print("MUTATION-NOT-CAUGHT")
    sys.exit(1)
print("MUTATION-CAUGHT")
