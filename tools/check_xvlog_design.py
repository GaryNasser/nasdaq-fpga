"""The five design files must compile standalone with xvlog.

The design must compile standalone with the real compiler - not just inside a test bench.

Round 238's conclusion was that claims needing Verilog syntax understanding should use `xvlog`, not a hand-written
parser. This applies that: **compile the five design files alone and require exit 0 with no errors.**

Why this is not already covered: the simulation suites compile design files *together with* a test bench, which can
mask a problem - a missing `include`, a module that only elaborates when a tb supplies something, or an order
dependency that happens to work in one list.

`xvlog` is the authority. No parsing by hand.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch")
VIVADO = r"D:\Xilinx\Vivado\2024.1\bin"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

files = sorted(f for f in os.listdir(RTL)
               if f.endswith(".v") and not f.startswith(("tb_", "test_")))

print("design files: %d" % len(files))
for f in files:
    print("   " + f)

env = dict(os.environ)
env["PATH"] = VIVADO + os.pathsep + env.get("PATH", "")

if not shutil.which("xvlog", path=env["PATH"]):
    print()
    print("XVLOG-SKIP (xvlog not on PATH - skipping is not passing)")
    sys.exit(2)

tmp = tempfile.mkdtemp(prefix="xvlog_design_")
try:
    args = ["xvlog", "--sv", "-i", RTL] + [os.path.join(RTL, f) for f in files]
    # xvlog is a .bat on Windows: it must be launched through the shell.
    cmd = " ".join('"%s"' % a if " " in a else a for a in args)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=tmp, env=env, timeout=900, shell=True)
    out = (r.stdout or "") + (r.stderr or "")

    errors = [l for l in out.split("\n") if "ERROR" in l]
    warnings = [l for l in out.split("\n") if "WARNING" in l]
    modules = [l for l in out.split("\n") if "analyzing module" in l]

    print()
    print("xvlog exit      : %d" % r.returncode)
    print("modules analysed: %d" % len(modules))
    print("errors          : %d" % len(errors))
    print("warnings        : %d" % len(warnings))

    for l in errors[:5]:
        print("   " + l.strip()[:88])
    for l in warnings[:5]:
        print("   " + l.strip()[:88])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
if r.returncode != 0 or errors:
    print("XVLOG-DESIGN-FAIL (the design does not compile on its own)")
    sys.exit(1)
if len(modules) != len(files):
    print("XVLOG-DESIGN-FAIL (%d files but %d modules analysed)" % (len(files), len(modules)))
    sys.exit(1)
print("XVLOG-DESIGN-PASS (%d files analyse cleanly with xvlog, %d modules)"
      % (len(files), len(modules)))
