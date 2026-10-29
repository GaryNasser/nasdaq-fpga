"""Prove check_ts_bin_math catches the stale '8 ns bucket' claim.

Round 21: a table row still said "256 x 8 ns buckets" eleven rounds after the narrative recorded that exact
mistake being fixed. This restores the wording and requires the check to notice.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = os.path.join(TOOLS, "check_ts_bin_math.py")

NEWROW = "| 直方图覆盖 | 0–2048 周期 = 0–10,779 ns（256 桶 × 每桶 8 **周期**；190 MHz 下 8 周期 = 42.11 ns） |"
OLDROW = "| 直方图覆盖 | 0–2040 ns（256 × 8 ns 桶） |"


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "TS-BIN-MATH-PASS" if "TS-BIN-MATH-PASS" in out0 else "?"))
if rc0 != 0:
    print("TS-BIN-MATH-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
st = os.stat(REPORT)
try:
    mutated = orig.replace(NEWROW, OLDROW, 1)
    landed = mutated != orig
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0 and "TS-BIN-MATH-FAIL" in out1
    print("restore '256 x 8 ns' wording   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, REPORT)
    os.utime(REPORT, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("TS-BIN-MATH-PROOF-PASS (a stale bucket-width claim is caught)")
    sys.exit(0)
print("TS-BIN-MATH-PROOF-FAIL")
sys.exit(1)
