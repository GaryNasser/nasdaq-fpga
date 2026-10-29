"""Prove check_build_wns fails if the WNS line reverts to the per-attempt log name."""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_build_wns.py")
SCRIPT = os.path.join(REPO, "scripts", "build.ps1")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("BUILD-WNS-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(SCRIPT, encoding="utf-8", errors="surrogateescape").read()
if "Get-Content $finalBuildLog | Select-String '^WNS:'" not in body:
    print("BUILD-WNS-PROOF-INCONCLUSIVE (the WNS line does not read finalBuildLog)")
    sys.exit(0)

bk = tempfile.mktemp(suffix=".ps1")
shutil.copyfile(SCRIPT, bk)
try:
    io.open(SCRIPT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(
        body.replace("Get-Content $finalBuildLog | Select-String '^WNS:'",
                     "Get-Content $buildLog | Select-String '^WNS:'"))
    print("reverted the WNS read to $buildLog")
    rc1, out1 = run()
    caught = rc1 != 0
    print("mutated : exit=%d %s" % (rc1, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, SCRIPT)
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if caught and rc2 == 0:
    print("BUILD-WNS-PROOF-PASS (reading the wrong log is caught)")
    sys.exit(0)
print("BUILD-WNS-PROOF-FAIL (caught=%s restored=%s)" % (caught, rc2 == 0))
sys.exit(1)
