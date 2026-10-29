"""Confirm check_falsepath_scope catches a pattern that grew too broad.

Three mutations, each of which would exempt paths nobody has measured:

  1. widen the -through to all of axi_interconnect_0  -> must FAIL
  2. retarget the -to at a datapath register          -> must FAIL
  3. anchor at the whole design (nasdaq_i/*)          -> must FAIL
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

XDC = r"D:\agent\nasdaq-fpga\vivado\timing_mcyc.xdc"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_falsepath_scope.py"

backup = tempfile.mktemp(suffix=".xdc")
shutil.copyfile(XDC, backup)
original = io.open(XDC, encoding="latin-1").read()

MUTATIONS = [
    ("widen -through", original.replace(
        "*axi_interconnect_0/s00_couplers/auto_pc/*aw_channel_0/aw_cmd_fsm_0/*",
        "*axi_interconnect_0/*", 1)),
    ("retarget -to", original.replace(
        "*ps7_0/inst/PS7_i/MAXIGP0WREADY",
        "*mold64_reasm_0/inst/*", 1)),
    ("whole design", original.replace(
        "*axi_interconnect_0/s00_couplers/auto_pc/*aw_channel_0/aw_cmd_fsm_0/*",
        "nasdaq_i/*", 1)),
]

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(XDC, "w", encoding="latin-1", newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-16s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(XDC, "w", encoding="latin-1", newline="\n").write(original)

restored = io.open(XDC, encoding="latin-1").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, XDC)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("FALSEPATH-GUARD-MUTATION-PASS")
else:
    print("FALSEPATH-GUARD-MUTATION-FAIL")
    sys.exit(1)
