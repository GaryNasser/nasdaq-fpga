"""Prove check_clock_marking fails when a 200 MHz mention loses its label.

The mutation removes the label I just added to L517 - the section 5.3 table - so the row reads
"PL 时钟实测 | 200.23 MHz" exactly as it did before this round. That is the state a reader would
find confusing: a table of current measurements giving the wrong clock.

It must fail.
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
CHK = os.path.join(REPO, "tools", "check_clock_marking.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Restore the pre-round row: strip the label and the current-frequency contrast.
OLD = ("| PL 时钟实测（**早期构建**）| **200.23 MHz**（`ts_hist` 自由计数器：200,227,539 cycles/s）；"
       "该构建的 PL 时钟为 200 MHz。**当前 bitstream 为 190 MHz**（见 §1），本节其余各项同属该早期构建 |")
NEW = "| PL 时钟实测 | **200.23 MHz**（`ts_hist` 自由计数器：200,227,539 cycles/s） |"

results = []
if OLD in original:
    mutated = original.replace(OLD, NEW, 1)
    bk = tempfile.mktemp(suffix=".md")
    shutil.copyfile(REPORT, bk)
    try:
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
                newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        results.append(("section 5.3 label removed", caught))
        detail = next((l.strip() for l in out.splitlines() if "UNMARKED" in l), "")
        print("%-28s exit=%d %s  %s" % ("section 5.3 label removed", rc,
                                        "CAUGHT" if caught else "MISSED", detail[:44]))
    finally:
        shutil.copyfile(bk, REPORT)
        os.unlink(bk)
else:
    print("%-28s NOT APPLIED (row text changed)" % "section 5.3 label removed")

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("CLOCK-MARKING-PROOF-FAIL")
sys.exit(1)
