"""Prove check_comparison_label catches a ratio table whose design column carries no provenance.

Round 12: the header read "| 口径 | A9 基线（实测） | PL | 加速比 |" - the baseline was labelled measured and the
PL column, which is a SIMULATION, was not.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = os.path.join(TOOLS, "check_comparison_label.py")

OLD = "| 口径 | A9 基线（实测） | PL（**仿真周期计数**，非板上端到端） | 加速比（仿真 vs 软件） |"
NEW = "| 口径 | A9 基线（实测） | PL | 加速比 |"


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, _ = run()
print("control : exit=%d" % rc0)
if rc0 != 0:
    print("COMPARISON-LABEL-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
st = os.stat(REPORT)
try:
    mutated = orig.replace(OLD, NEW, 1)
    landed = mutated != orig
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0 and "COMPARISON-LABEL-FAIL" in out1
    print("unlabel the PL column   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, REPORT)
    os.utime(REPORT, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("COMPARISON-LABEL-PROOF-PASS (an unlabelled design column is caught)")
    sys.exit(0)
print("COMPARISON-LABEL-PROOF-FAIL")
sys.exit(1)
