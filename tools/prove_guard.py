"""Widen the guard's bound so absurd values pass, and require check_guard to fail.

    L476   wall_cycles_max = (t1 - t0) * PL_CLK_MHZ * 1e6 * 1.5 + 1e6
    L477   if cycles > wall_cycles_max:
    L478       print("WARN-IMPLAUSIBLE: ...")

Making the bound effectively infinite reproduces "the guard did NOT fire on corrupt data" -
one of the three conditions check_guard exists to test.

The check runs the driver through a mock overlay, so the edit reaches it without a board.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
DRV = os.path.join(REPO, "board", "load_overlay.py")
CHK = os.path.join(TOOLS, "check_guard.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


drv = io.open(DRV, encoding="utf-8", errors="replace").read()

OLD = "wall_cycles_max = (t1 - t0) * PL_CLK_MHZ * 1e6 * 1.5 + 1e6"
NEW = "wall_cycles_max = 1e30   # MUTATION: the guard can never fire"

if OLD not in drv:
    print("GUARD-PROOF-FAIL (bound line not found)")
    sys.exit(1)

mutated = drv.replace(OLD, NEW, 1)
print("guard bound widened to 1e30")
print()

results = []
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, bk)
try:
    io.open(DRV, "w", encoding="utf-8", errors="replace", newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    results.append(("guard never fires", caught))
    for l in out.splitlines():
        if "FAIL" in l or "did NOT fire" in l or "GUARD" in l:
            print("   %s" % l.strip()[:90])
    print("   exit=%d %s" % (rc, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, DRV)
    os.unlink(bk)

rc2, out2 = run()
print()
print("restored exit=%d" % rc2)

if caught and rc2 == 0:
    sys.exit(0)
print("GUARD-PROOF-FAIL")
sys.exit(1)
