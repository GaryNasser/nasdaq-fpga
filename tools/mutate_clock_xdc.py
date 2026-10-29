"""Prove check_clock_xdc catches a second parse that stops applying cleanly.

The check's whole purpose is to notice if the constraint file ever starts warning AFTER
synthesis - the state where constraints silently do not apply, hidden among the 105
warnings the first parse produces.

This injects a realistic complaint into the log after the second parse and confirms
the check fails, then restores the log and confirms it passes.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

LOG = r"D:\agent\nasdaq-fpga\build_check\rebuild.log"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_clock_xdc.py"

backup = tempfile.mktemp(suffix=".log")
shutil.copyfile(LOG, backup)

original = io.open(LOG, encoding="utf-8", errors="replace").read()
lines = original.split("\n")

# Find the second parse and inject a complaint just after it.
parses = [i for i, l in enumerate(lines)
          if "Parsing XDC File" in l and "timing_mcyc.xdc" in l
          and "Finished" not in l]
assert len(parses) >= 2, "expected two parses"

plant = ("CRITICAL WARNING: [Vivado 12-4739] set_clock_groups:No valid object(s) "
         "found for '-group [get_clocks clk_fpga_0]'. "
         "[D:/agent/nasdaq-fpga/vivado/timing_mcyc.xdc:26]")

injected = lines[:parses[1] + 1] + [plant] + lines[parses[1] + 1:]
io.open(LOG, "w", encoding="utf-8", errors="replace", newline="\n").write(
    "\n".join(injected))

landed = plant in io.open(LOG, encoding="utf-8", errors="replace").read()
print("mutation landed: %s" % landed)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("check exit code: %d" % r.returncode)
for l in (r.stdout or "").strip().splitlines()[-4:]:
    print("  " + l)

shutil.copyfile(backup, LOG)
os.unlink(backup)
restored = io.open(LOG, encoding="utf-8", errors="replace").read() == original
print("restored: %s" % restored)

r2 = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r2.returncode)

print()
if landed and r.returncode != 0 and restored and r2.returncode == 0:
    print("CLOCK-XDC-MUTATION-PASS")
else:
    print("CLOCK-XDC-MUTATION-FAIL")
    sys.exit(1)
