"""Test check_golden's failure branch by corrupting GOLDEN_BOOK in the driver.

The check compares three sources of the same numbers:

    docs/measurements/baseline-a9.txt   BOOK-COUNTERS: add=... exe=...
    board/load_overlay.py               GOLDEN_BOOK = {'add': ..., ...}
    the simulation's BOOK-PASS line

Corrupting one entry of GOLDEN_BOOK must produce GOLDEN-CONST-FAIL and a non-zero exit.
Before the fix it produced the FAIL text and exited 0, so the suite recorded PASS.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHECK = os.path.join(REPO, "tools", "check_golden.py")
DRV = os.path.join(REPO, "board", "load_overlay.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

original = io.open(DRV, encoding="utf-8").read()
backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, backup)

m = re.search(r"GOLDEN_BOOK\s*=\s*\{(.*?)\}", original, re.S)
if not m:
    print("GOLDEN_BOOK not found; aborting")
    sys.exit(2)

first_kv = re.search(r"'(\w+)':\s*(\d+)", m.group(1))
key, val = first_kv.group(1), int(first_kv.group(2))
print("corrupting GOLDEN_BOOK['%s'] from %d to %d" % (key, val, val + 1))

mutated = original.replace(first_kv.group(0), "'%s': %d" % (key, val + 1), 1)
landed = mutated != original
io.open(DRV, "w", encoding="utf-8", newline="\n").write(mutated)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
out = (r.stdout or "") + (r.stderr or "")

print("  mutation landed    : %s" % landed)
print("  FAIL token printed : %s" % ("GOLDEN-CONST-FAIL" in out))
print("  exit code          : %d" % r.returncode)

ok = landed and "GOLDEN-CONST-FAIL" in out and r.returncode != 0

shutil.copyfile(backup, DRV)
os.unlink(backup)
restored = io.open(DRV, encoding="utf-8").read() == original
print("  restored           : %s" % restored)

r2 = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
print("  healthy exit       : %d" % r2.returncode)

print()
if ok and restored and r2.returncode == 0:
    print("GOLDEN-EXIT-PASS")
else:
    print("GOLDEN-EXIT-FAIL")
    sys.exit(1)
