import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\\agent\\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHK = os.path.join(TOOLS, "check_board_claims.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Plant a board result that states no run count, in a place with no count nearby.
TARGET = ("| `mold64_reasm` | 仿真 850/850 包、43428/43428 消息；**板上实测 849 包、43379 条，`gap=1`、`err=1463`**（n=1） |")
if TARGET not in rep:
    print("BOARD-CLAIM-MUTATION-FAIL (anchor row not found)")
    sys.exit(1)

mutated = rep.replace(TARGET, "| `mold64_reasm` | 仿真 850/850 包、43428/43428 消息；板上实测 849 包、43379 条 |", 1)
if mutated == rep:
    print("BOARD-CLAIM-MUTATION-FAIL (mutation did not land)")
    sys.exit(1)
print("  removed the (n=1) count from the table row")

bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    caught = r.returncode != 0
    print("  with the run count removed:")
    for l in out.splitlines():
        if "NO COUNT" in l or "BOARD-CLAIM" in l:
            print("     " + l.strip()[:86])
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

r2 = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
print()
print("  restored exit=%d" % r2.returncode)
print()
if caught and r2.returncode == 0:
    print("BOARD-CLAIM-MUTATION-PASS")
    sys.exit(0)
print("BOARD-CLAIM-MUTATION-FAIL")
sys.exit(1)
