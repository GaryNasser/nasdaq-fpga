"""Prove the retargeted check fails when the report's counters disagree with a fresh baseline run.

The mutation changes the report's line from orders=320 to orders=999. Before this round the check
would have passed - it compared against its own GOLD constant. Now the constant IS the report, so
the mutation must fail.
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
CHK = os.path.join(REPO, "tools", "check_baseline_repro.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
m = re.search(r"BOOK-COUNTERS:\s*add=15334[^\n]*?orders=(\d+)", rep)
if not m:
    print("BASELINE-GOLD-PROOF-FAIL (no BOOK-COUNTERS line in the report)")
    sys.exit(1)

mutated = rep[:m.start(1)] + "999" + rep[m.end(1):]

results = []
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    results.append(("report orders=320 -> 999", caught))
    detail = next((l.strip() for l in out.splitlines()
                   if "MISMATCH" in l or "FAIL" in l), "")
    print("%-26s exit=%d %s  %s" % ("report orders=320 -> 999", rc,
                                    "CAUGHT" if caught else "MISSED", detail[:40]))
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("BASELINE-GOLD-PROOF-FAIL")
sys.exit(1)
