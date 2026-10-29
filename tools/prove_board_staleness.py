"""Prove check_board_staleness fails when the caveat is gone.

Round 25: the caveat must name an archive and sit beside a citation. Removing it should leave the citations bare.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = os.path.join(TOOLS, "check_board_staleness.py")

MARK = "> **关于第 15–18 轮这些板上数字的时效**"


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "BOARD-STALENESS-PASS" if "BOARD-STALENESS-PASS" in out0 else "?"))
if rc0 != 0:
    print("BOARD-STALENESS-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
st = os.stat(REPORT)
try:
    lines = orig.split("\n")
    keep = [l for l in lines if MARK not in l]
    mutated = "\n".join(keep)
    landed = mutated != orig
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0 and "BOARD-STALENESS-FAIL" in out1
    print("remove the caveat   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, REPORT)
    os.utime(REPORT, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("BOARD-STALENESS-PROOF-PASS (uncited board figures are caught)")
    sys.exit(0)
print("BOARD-STALENESS-PROOF-FAIL")
sys.exit(1)
