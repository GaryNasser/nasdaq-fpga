"""Prove the fixed check catches a PL transfer that enables without resetting.

Round 87 found it passed that defect. The mutation: delete the CTRL 0x2 reset from the --book
path, leaving 0x1 (enable) above the transfer.

    before the fix   FLAG-AUDIT-PASS   (it checked the VALUE of the nearest write)
    after the fix    must FAIL          (it now requires a reset above the transfer)
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
CHK = os.path.join(TOOLS, "check_transfer_reset.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


drv = io.open(DRV, encoding="utf-8", errors="replace").read()
lines = drv.split("\n")

# Remove the 0x2 reset in the --book region (after line 400).
target = None
for i, l in enumerate(lines, 1):
    if "REG_M64_CTRL" in l and "0x2" in l and 200 < i < 300:
        target = i
        break

if target is None:
    print("TRANSFER-RESET-PROOF-FAIL (no 0x2 reset in the --pipeline path)")
    sys.exit(1)

print("removing the --pipeline CTRL 0x2 reset at line %d" % target)
print("   %s" % lines[target - 1].strip()[:80])
print()

mutated = "\n".join(lines[:target - 1] + lines[target:])
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, bk)
try:
    io.open(DRV, "w", encoding="utf-8", errors="replace", newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    for l in out.splitlines():
        if l.strip():
            print("   %s" % l.strip()[:92])
    print("   exit=%d %s" % (rc, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, DRV)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)

if caught and rc2 == 0:
    sys.exit(0)
print("TRANSFER-RESET-PROOF-FAIL")
sys.exit(1)
