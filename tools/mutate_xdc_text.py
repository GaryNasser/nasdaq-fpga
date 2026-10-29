"""Prove check_xdc_clock_text catches a stale frequency presented as current.

The class of error it guards: a comment saying "200 MHz" as though it were the design
clock, after the design moved to 190 MHz. That is precisely what round 32 found in five
places.

Two mutations:
  1. re-state 200 MHz as current in a plain comment   -> must FAIL
  2. state 200 MHz with a historical marker           -> must pass
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

XDC = r"D:\agent\nasdaq-fpga\vivado\timing_mcyc.xdc"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_xdc_clock_text.py"

backup = tempfile.mktemp(suffix=".xdc")
shutil.copyfile(XDC, backup)
original = io.open(XDC, encoding="latin-1").read()

results = []

# 1. stale, presented as current
stale_line = "# All datapath logic runs at 200 MHz and is fully constrained.\n"
mut = original + stale_line
io.open(XDC, "w", encoding="latin-1", newline="\n").write(mut)
landed = stale_line in io.open(XDC, encoding="latin-1").read()
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
results.append(("stale as current", landed, r.returncode != 0))
print("stale as current      landed=%s exit=%d %s"
      % (landed, r.returncode, "CAUGHT" if r.returncode else "MISSED"))

# 2. same figure, marked historical
hist_line = "# All datapath logic originally ran at 200 MHz.\n"
mut = original + hist_line
io.open(XDC, "w", encoding="latin-1", newline="\n").write(mut)
landed = hist_line in io.open(XDC, encoding="latin-1").read()
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
results.append(("historical marker", landed, r.returncode == 0))
print("marked historical     landed=%s exit=%d %s"
      % (landed, r.returncode, "PASSES (correct)" if r.returncode == 0 else "FAILS (wrong)"))

io.open(XDC, "w", encoding="latin-1", newline="\n").write(original)
restored = io.open(XDC, encoding="latin-1").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, XDC)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("XDC-TEXT-MUTATION-PASS")
else:
    print("XDC-TEXT-MUTATION-FAIL")
    sys.exit(1)
