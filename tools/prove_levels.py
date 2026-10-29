"""Prove check_levels_derive fails when the level count disagrees with the capture.

    1  levels=95 -> levels=96   (a wrong count)
    2  the capture swapped for a different file is out of scope; the count mutation is enough

Must fail.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHK = os.path.join(REPO, "tools", "check_levels_derive.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
m = re.search(r"levels=(\d+)", rep)
if not m:
    print("LEVELS-PROOF-FAIL (no levels= in the report)")
    sys.exit(1)

mutated = rep[:m.start(1)] + "96" + rep[m.end(1):]

results = []
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    results.append(("levels 95 -> 96", caught))
    detail = next((l.strip() for l in out.splitlines() if "MISMATCH" in l), "")
    print("%-22s exit=%d %s  %s" % ("levels 95 -> 96", rc,
                                    "CAUGHT" if caught else "MISSED", detail[:44]))
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("LEVELS-PROOF-FAIL")
sys.exit(1)
