"""Prove check_rtl_parity fails when synthesis lists a design file that no simulation compiles."""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_rtl_parity.py")
TCL = os.path.join(REPO, "vivado", "create_project.tcl")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("PARITY-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(TCL, encoding="utf-8", errors="surrogateescape").read()
m = [l for l in body.split("\n") if ".v" in l]
if not m:
    print("PARITY-PROOF-INCONCLUSIVE (no .v line in the tcl)")
    sys.exit(0)

bk = tempfile.mktemp(suffix=".tcl")
shutil.copyfile(TCL, bk)
try:
    line = m[0]
    mutated = body.replace(line, line + "\n" + line.replace("\n", " ").strip().split()[0] + " never_simulated.v",
                           1) if line.strip() else body
    io.open(TCL, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0
    named = "never_simulated" in out1
    print("mutated : exit=%d %s%s" % (rc1, "CAUGHT" if caught else "MISSED",
                                      "" if named else "  (but does not name it)"))
    if not caught:
        for l in [x for x in out1.split("\n") if x.strip()][-4:]:
            print("   " + l.strip()[:80])
finally:
    shutil.copyfile(bk, TCL)
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if caught and named and rc2 == 0:
    print("PARITY-PROOF-PASS (a synthesised-only file is caught and named)")
    sys.exit(0)
print("PARITY-PROOF-FAIL (caught=%s named=%s restored=%s)" % (caught, named, rc2 == 0))
sys.exit(1)
