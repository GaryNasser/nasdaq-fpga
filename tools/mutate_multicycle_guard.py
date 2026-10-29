"""Confirm check_multicycle_guard catches the exception being re-added.

Two mutations:
  1. restore the two set_multicycle_path lines -> must FAIL
  2. delete the REMOVED history block          -> must FAIL
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

XDC = r"D:\agent\nasdaq-fpga\vivado\timing_mcyc.xdc"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_multicycle_guard.py"

backup = tempfile.mktemp(suffix=".xdc")
shutil.copyfile(XDC, backup)
original = io.open(XDC, encoding="latin-1").read()

results = []

# 1. re-add the exception
plant = ("\nset_multicycle_path 2 -setup -through [get_pins -hierarchical -filter "
         "{NAME =~ *mold64_reasm_0/inst/gap_pending_reg/D}]\n")
mut = original + plant
io.open(XDC, "w", encoding="latin-1", newline="\n").write(mut)
landed = "set_multiple_path" in mut or plant in io.open(XDC, encoding="latin-1").read()
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
results.append(("re-added exception", landed, r.returncode != 0))
print("re-added exception   landed=%s exit=%d %s"
      % (landed, r.returncode, "CAUGHT" if r.returncode else "MISSED"))

# 2. remove the history block
mut = original.replace("# REMOVED (round 33)", "# (history elided)")
io.open(XDC, "w", encoding="latin-1", newline="\n").write(mut)
landed = "REMOVED (round 33)" not in io.open(XDC, encoding="latin-1").read()
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
results.append(("history removed", landed, r.returncode != 0))
print("history removed      landed=%s exit=%d %s"
      % (landed, r.returncode, "CAUGHT" if r.returncode else "MISSED"))

io.open(XDC, "w", encoding="latin-1", newline="\n").write(original)
restored = io.open(XDC, encoding="latin-1").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, XDC)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("MULTICYCLE-GUARD-MUTATION-PASS")
else:
    print("MULTICYCLE-GUARD-MUTATION-FAIL")
    sys.exit(1)
