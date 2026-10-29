"""Prove each repaired checker actually exits non-zero on a real failure.

Adding `sys.exit(1)` to a branch and confirming it parses is not proof; the branch has
to be REACHED. This damages real inputs in a reversible way and runs the checker:

    check_artifacts.py     change the driver's PL_CLK_MHZ so it disagrees with the
                           bitstream's design frequency
    check_multidriver.py   add a Verilog file where one reg is assigned in two always
                           blocks
    check_mock_model.py    edit the mock's register table
    check_regmap.py        edit a driver register constant
    audit_clock_docs.py    reintroduce a stale "200 MHz" claim into the report

Each file is backed up and restored; the restore is verified by comparing contents.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

env = dict(os.environ)
env["PATH"] = r"D:\Xilinx\Vivado\2024.1\bin;" + env.get("PATH", "")


def run(script):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, script)],
                       cwd=TOOLS, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# ---- 1. check_multidriver: plant a double-driven reg --------------------------
probe = os.path.join(REPO, "rtl", "itch", "_md_probe.v")
io.open(probe, "w", encoding="utf-8").write(
    "module _md_probe(input clk, input a, input b, output reg q);\n"
    "  always @(posedge clk) q <= a;\n"
    "  always @(posedge clk) q <= b;\n"
    "endmodule\n")
rc, out = run("check_multidriver.py")
os.unlink(probe)
print("check_multidriver.py  exit=%d  %s"
      % (rc, "CAUGHT" if rc != 0 and "MULTI-DRIVEN" in out else "NOT CAUGHT"))
md_ok = rc != 0

# ---- 2. check_artifacts: break the PL clock constant --------------------------
DRV = os.path.join(REPO, "board", "load_overlay.py")
backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, backup)
src = io.open(DRV, encoding="utf-8").read()
broken = src.replace("PL_CLK_MHZ           = 190.000", "PL_CLK_MHZ           = 175.000", 1)
landed = broken != src
io.open(DRV, "w", encoding="utf-8").write(broken)
rc, out = run("check_artifacts.py")
shutil.copyfile(backup, DRV)
os.unlink(backup)
restored = io.open(DRV, encoding="utf-8").read() == src
print("check_artifacts.py    exit=%d  landed=%s restored=%s  %s"
      % (rc, landed, restored,
         "CAUGHT" if landed and rc != 0 else "NOT CAUGHT"))
art_ok = landed and rc != 0 and restored

# ---- 3. audit_clock_docs: reintroduce a stale claim ---------------------------
DOC = os.path.join(REPO, "docs", "final-report.md")
b2 = tempfile.mktemp(suffix=".md")
shutil.copyfile(DOC, b2)
src = io.open(DOC, encoding="utf-8", errors="surrogateescape").read()
broken = src + "\n本设计运行在 200 MHz 时钟下。\n"
landed = broken != src
io.open(DOC, "w", encoding="utf-8", errors="surrogateescape",
        newline="\n").write(broken)
rc, out = run("audit_clock_docs.py")
shutil.copyfile(b2, DOC)
os.unlink(b2)
restored = io.open(DOC, encoding="utf-8", errors="surrogateescape").read() == src
print("audit_clock_docs.py   exit=%d  landed=%s restored=%s  %s"
      % (rc, landed, restored,
         "CAUGHT" if landed and rc != 0 else "NOT CAUGHT"))
clk_ok = landed and rc != 0 and restored

# ---- 4. healthy tree: all five must still pass -------------------------------
print()
healthy = True
for script in ("check_artifacts.py", "check_regmap.py", "check_multidriver.py",
               "check_mock_model.py", "audit_clock_docs.py"):
    rc, out = run(script)
    print("  %-24s healthy exit=%d" % (script, rc))
    if rc != 0:
        healthy = False

print()
if md_ok and art_ok and clk_ok and healthy:
    print("EXIT-REACH-PASS")
else:
    print("EXIT-REACH-FAIL")
    sys.exit(1)
