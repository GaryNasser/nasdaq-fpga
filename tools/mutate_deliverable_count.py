"""Confirm check_deliverable_count catches the DMA item being counted as delivered.

The regression to guard against is exactly what this round fixed: the audit treating an
explicitly-unmeasured item as present, and reporting 11 of 13.

The mutation restores the original pattern-based test, which returns True because §11.4
mentions numbers near the phrase while saying the opposite.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

AUDIT = r"D:\agent\nasdaq-fpga\tools\audit_deliverables.py"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_deliverable_count.py"

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(AUDIT, backup)
original = io.open(AUDIT, encoding="utf-8").read()

# Replace the honest `lambda: False` for the DMA item with a pattern that matches the
# report's §11.4 sentence - the old failure mode.
# Round 257: DMA and K2 are measured now, so the old mutation (claiming DMA delivered) no longer
# describes a failure. K1 is the only true gap, and the equivalent fault is claiming K1 delivered.
OLD = """     lambda: False,
     "PYNQ-Z2 无 PL 侧以太网引脚"),"""
NEW = """     lambda: True,
     "已交付"),"""

mutated = original.replace(OLD, NEW, 1)
landed = mutated != original
io.open(AUDIT, "w", encoding="utf-8", newline="\n").write(mutated)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("mutation landed: %s" % landed)
print("check exit code: %d" % r.returncode)
for line in (r.stdout or "").strip().splitlines()[-4:]:
    print("  " + line)

shutil.copyfile(backup, AUDIT)
os.unlink(backup)
restored = io.open(AUDIT, encoding="utf-8").read() == original
print("restored: %s" % restored)

r2 = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r2.returncode)

print()
if landed and r.returncode != 0 and restored and r2.returncode == 0:
    print("DELIVERABLE-COUNT-MUTATION-PASS")
else:
    print("DELIVERABLE-COUNT-MUTATION-FAIL")
    sys.exit(1)
