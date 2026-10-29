"""Prove check_book_hist fails on a per-type counter change that a total would hide.

The interesting mutation: move one message between two types. Total stays 43,428, so a check that
compared only totals would pass - but the book cannot have processed 15,335 adds when the capture
holds 15,334.

    1  add 15334 -> 15335            (total unchanged, add wrong)
    2  exe 7 -> 8                    (the smallest counter, easiest to overlook)
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
CHK = os.path.join(REPO, "tools", "check_book_hist.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

CASES = [
    ("add 15334 -> 15335", rep.replace("add=15334", "add=15335", 1)),
    ("exe 7 -> 8", rep.replace("exe=7", "exe=8", 1)),
]

results = []
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    for label, mutated in CASES:
        if mutated == rep:
            print("%-24s NOT APPLIED" % label)
            continue
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
                newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        results.append((label, caught))
        detail = next((l.strip() for l in out.splitlines() if "MISMATCH" in l), "")
        print("%-24s exit=%d %s  %s" % (label, rc, "CAUGHT" if caught else "MISSED",
                                        detail[:40]))
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("BOOK-HIST-PROOF-FAIL")
sys.exit(1)
