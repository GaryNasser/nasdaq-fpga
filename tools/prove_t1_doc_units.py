"""Prove check_t1_doc_units catches the wording that survived eleven rounds.

Round 21: a table row said "256 x 8 ns buckets, 0-2040 ns" while the RTL makes a bucket 8 CYCLES.
`check_t1_units` compares RTL against driver and never read the report, so it passed throughout.

This puts the exact old wording back and requires the new check to see it.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = os.path.join(TOOLS, "check_t1_doc_units.py")

GOOD = "| 直方图覆盖 | 0–2048 周期 = 0–10,779 ns（256 桶 × 每桶 8 **周期**；190 MHz 下 8 周期 = 42.11 ns） |"
BAD = "| 直方图覆盖 | 0–2040 ns（256 × 8 ns 桶） |"


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "T1-DOC-UNITS-PASS" if "T1-DOC-UNITS-PASS" in out0 else "?"))
if rc0 != 0:
    print("T1-DOC-UNITS-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
st = os.stat(REPORT)
try:
    mutated = orig.replace(GOOD, BAD, 1)
    landed = mutated != orig
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0 and "T1-DOC-UNITS-FAIL" in out1
    print("restore the round-21 wording   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
    if caught:
        for l in out1.split("\n"):
            if "coverage" in l and "clock-period" in l:
                print("  " + l.strip()[:88])
                break
finally:
    shutil.copyfile(bk, REPORT)
    os.utime(REPORT, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("T1-DOC-UNITS-PROOF-PASS (the wording that survived eleven rounds is caught)")
    sys.exit(0)
print("T1-DOC-UNITS-PROOF-FAIL")
sys.exit(1)
