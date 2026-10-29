"""Prove check_xvlog_design fails when a design file does not compile."""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_xvlog_design.py")
RTL = os.path.join(REPO, "rtl", "itch")
VICTIM = os.path.join(RTL, "ts_hist.v")

env = dict(os.environ)
env["PATH"] = r"D:\Xilinx\Vivado\2024.1\bin" + os.pathsep + env.get("PATH", "")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), env=env, timeout=900)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("XVLOG-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(VICTIM, encoding="latin-1").read()
bk = tempfile.mktemp(suffix=".v")
shutil.copyfile(VICTIM, bk)
try:
    # A syntactically broken file: an unbalanced begin.
    mutated = body.replace("endmodule", "  begin\nendmodule", 1)
    io.open(VICTIM, "w", encoding="latin-1", newline="\n").write(mutated)
    print("injected an unbalanced begin into ts_hist.v")
    rc1, out1 = run()
    caught = rc1 != 0
    print("mutated : exit=%d %s" % (rc1, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, VICTIM)
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if caught and rc2 == 0:
    print("XVLOG-PROOF-PASS (a design file that does not compile is caught)")
    sys.exit(0)
print("XVLOG-PROOF-FAIL (caught=%s restored=%s)" % (caught, rc2 == 0))
sys.exit(1)
