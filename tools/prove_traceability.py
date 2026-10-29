"""Prove check_traceability fails when the measurement records are gone.

Round 12 found that removing any SINGLE archive does not fail the check, because the defect log carries the same
figures in its run records. That is a property of how this project logs, not a weakness - but it means the proof must
remove the whole archive set, not one file.
"""
import glob
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
MEAS = r"D:\agent\nasdaq-fpga\docs\measurements"
CHECK = os.path.join(TOOLS, "check_traceability.py")


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "TRACEABILITY-PASS" if "TRACEABILITY-PASS" in out0 else "?"))
if rc0 != 0:
    print("TRACEABILITY-PROOF-FAIL (control does not pass)")
    sys.exit(1)

targets = sorted(glob.glob(os.path.join(MEAS, "*.txt")))
if not targets:
    print("TRACEABILITY-PROOF-INCONCLUSIVE (no archives)")
    sys.exit(0)

print("archives to remove: %d" % len(targets))
kept = []
caught = False
try:
    for p in targets:
        st = os.stat(p)
        bk = tempfile.mktemp(suffix=".txt")
        shutil.copyfile(p, bk)
        kept.append((p, bk, st))
        os.unlink(p)
    rc1, out1 = run()
    caught = rc1 != 0 and "ASSERTED" in out1
    print("remove all archives       landed=True exit=%d %s"
          % (rc1, "CAUGHT" if caught else "MISSED"))
    if caught:
        for line in out1.split("\n"):
            if "TRACEABILITY-FAIL" in line:
                print("  " + line.strip()[:80])
finally:
    for p, bk, st in kept:
        shutil.copyfile(bk, p)
        os.utime(p, (st.st_atime, st.st_mtime))
        os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d %s" % (rc2, "TRACEABILITY-PASS" if "TRACEABILITY-PASS" in out2 else "?"))
print()
if caught and rc2 == 0:
    print("TRACEABILITY-PROOF-PASS (with no archives, the sweep names untraceable figures)")
    sys.exit(0)
print("TRACEABILITY-PROOF-FAIL (caught=%s restored=%s)" % (caught, rc2 == 0))
sys.exit(1)
