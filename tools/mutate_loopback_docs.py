"""Confirm check_loopback_docs catches both directions of drift.

  1. help text reverts to the bare "M1: DMA loopback test"    -> must FAIL
  2. the BD gains loopback_dma while help still says unavailable -> must FAIL (stale)
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

DRV = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
TCL = r"D:\agent\nasdaq-fpga\vivado\create_project.tcl"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_loopback_docs.py"

drv_backup = tempfile.mktemp(suffix=".py")
tcl_backup = tempfile.mktemp(suffix=".tcl")
shutil.copyfile(DRV, drv_backup)
# Round 253: interruption-safe restore. A killed run must not leave a source file modified.
import atexit as _atexit
_atexit.register(lambda _d=DRV, _b=drv_backup: os.path.exists(_b) and shutil.copyfile(_b, _d))

shutil.copyfile(TCL, tcl_backup)
drv_orig = io.open(DRV, encoding="utf-8").read()
tcl_orig = io.open(TCL, encoding="utf-8", errors="replace").read()

results = []

# 1. revert the help text
mut = drv_orig.replace("NOT available on this overlay", "available on this overlay", 1)
io.open(DRV, "w", encoding="utf-8", newline="\n").write(mut)
landed = mut != drv_orig
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
results.append(("bare help text", landed, r.returncode != 0))
print("bare help text       landed=%-5s exit=%d %s"
      % (landed, r.returncode, "CAUGHT" if r.returncode else "MISSED"))
io.open(DRV, "w", encoding="utf-8", newline="\n").write(drv_orig)

# 2. the BD gains the IP -> the warning becomes stale
mut_tcl = tcl_orig + "\n# loopback_dma added\ncreate_bd_cell -type ip -vlnv x loopback_dma_0\n"
io.open(TCL, "w", encoding="utf-8", errors="replace", newline="\n").write(mut_tcl)
landed2 = mut_tcl != tcl_orig
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
results.append(("stale warning", landed2, r.returncode != 0))
print("stale warning        landed=%-5s exit=%d %s"
      % (landed2, r.returncode, "CAUGHT" if r.returncode else "MISSED"))
io.open(TCL, "w", encoding="utf-8", errors="replace", newline="\n").write(tcl_orig)

restored = (io.open(DRV, encoding="utf-8").read() == drv_orig
            and io.open(TCL, encoding="utf-8", errors="replace").read() == tcl_orig)
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(drv_backup, DRV)
shutil.copyfile(tcl_backup, TCL)
os.unlink(drv_backup)
os.unlink(tcl_backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("LOOPBACK-DOC-MUTATION-PASS")
else:
    print("LOOPBACK-DOC-MUTATION-FAIL")
    sys.exit(1)
