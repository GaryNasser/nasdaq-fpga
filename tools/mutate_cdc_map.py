"""Confirm check_cdc_map catches a topology change that creates a new CDC.

Two mutations:

  1. move ps7_0/M_AXI_GP0_ACLK from clk_200m to fclk0 - which would put the control
     plane across the domains with NO converter;
  2. give axi_interconnect_0 a second clock - which would make it span domains while
     the report still claims single-domain.

Both are changes that an asynchronous clock group would silently absorb.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TCL = r"D:\agent\nasdaq-fpga\vivado\create_project.tcl"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_cdc_map.py"

backup = tempfile.mktemp(suffix=".tcl")
shutil.copyfile(TCL, backup)
original = io.open(TCL, encoding="utf-8", errors="replace").read()

results = []

# --- mutation 1: move GP0_ACLK to fclk0 -------------------------------------
m1 = original
if "M_AXI_GP0_ACLK" in original:
    # Append an overriding connection on fclk0: the last connect wins in Vivado.
    m1 = original + ("\nconnect_bd_net -net fclk0 [get_bd_pins ps7_0/M_AXI_GP0_ACLK]\n")
land1 = m1 != original
io.open(TCL, "w", encoding="utf-8", errors="replace", newline="\n").write(m1)
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
results.append(("GP0 moved to fclk0", land1, r.returncode != 0))
print("GP0 moved to fclk0      landed=%s exit=%d %s"
      % (land1, r.returncode, "CAUGHT" if r.returncode else "MISSED"))

# --- mutation 2: second clock on axi_interconnect_0 -------------------------
m2 = original + ("\nconnect_bd_net -net fclk0 [get_bd_pins axi_interconnect_0/M00_ACLK]\n")
io.open(TCL, "w", encoding="utf-8", errors="replace", newline="\n").write(m2)
land2 = m2 != original
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
results.append(("interconnect two clocks", land2, r.returncode != 0))
print("interconnect two clocks landed=%s exit=%d %s"
      % (land2, r.returncode, "CAUGHT" if r.returncode else "MISSED"))

io.open(TCL, "w", encoding="utf-8", errors="replace", newline="\n").write(original)
restored = io.open(TCL, encoding="utf-8", errors="replace").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, TCL)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("CDC-MAP-MUTATION-PASS")
else:
    print("CDC-MAP-MUTATION-FAIL")
    sys.exit(1)
