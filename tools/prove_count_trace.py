"""Prove check_count_trace fails when the report's count disagrees with the capture.

Two mutations:

    1  the report states 851/851 packets instead of 850/850
    2  the capture is truncated, so the walk yields fewer messages

The second is the more interesting: it shows the check is anchored to the DATA, not to a constant
someone typed. If only the report changed and the data did not, the check must fail; if the data
changed, the check must fail too, because the report then describes a capture that is not there.
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
MOLD = os.path.join(REPO, "data", "itch_loc6836.mold64")
CHK = os.path.join(REPO, "tools", "check_count_trace.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


results = []

# 1. Report states a different packet count.
rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
m = re.search(r"850/850 包", rep)
if m:
    mutated = rep[:m.start()] + "851/851 包" + rep[m.end():]
    bk = tempfile.mktemp(suffix=".md")
    shutil.copyfile(REPORT, bk)
    try:
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
                newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        results.append(("report says 851/851", caught))
        print("%-30s exit=%d %s" % ("report says 851/851", rc,
                                    "CAUGHT" if caught else "MISSED"))
    finally:
        shutil.copyfile(bk, REPORT)
        os.unlink(bk)
else:
    print("%-30s NOT APPLIED" % "report says 851/851")

# 2. Truncate the capture: the report then names a capture that is not there.
bk = tempfile.mktemp(suffix=".mold64")
shutil.copyfile(MOLD, bk)
try:
    body = open(MOLD, "rb").read()
    io.open(MOLD, "wb").write(body[:len(body) // 2])
    rc, out = run()
    caught = rc != 0
    results.append(("capture truncated", caught))
    print("%-30s exit=%d %s" % ("capture truncated", rc,
                                "CAUGHT" if caught else "MISSED"))
    # What the walk produced.
    got = [l.strip() for l in out.splitlines() if "packets" in l][:1]
    if got:
        print("   %s" % got[0][:60])
finally:
    shutil.copyfile(bk, MOLD)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("COUNT-TRACE-PROOF-FAIL")
sys.exit(1)
