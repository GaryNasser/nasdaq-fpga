"""Prove check_baseline_mirror catches the C baseline drifting from the RTL.

Round 19: the C file kept the pre-round-7 full test for twelve rounds. This puts it back and requires the
mirror check to notice.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
C = r"D:\agent\nasdaq-fpga\sw\baseline\itch_book_baseline.c"
CHECK = os.path.join(TOOLS, "check_baseline_mirror.py")

OLD = "if (b->level_cnt >= LEVELS)\n        return -1;"
NEW = "if (b->next_free_level >= LEVELS - 1)\n        return -1;"


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "BASELINE-MIRROR-PASS" if "BASELINE-MIRROR-PASS" in out0 else "?"))
if rc0 != 0:
    print("BASELINE-MIRROR-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(C, encoding="utf-8", errors="replace").read()
bk = tempfile.mktemp(suffix=".c")
shutil.copyfile(C, bk)
st = os.stat(C)
try:
    mutated = orig.replace(OLD, NEW, 1)
    landed = mutated != orig
    io.open(C, "w", encoding="utf-8", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0 and "BASELINE-MIRROR-FAIL" in out1
    print("restore the pre-round-7 full test   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, C)
    os.utime(C, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("BASELINE-MIRROR-PROOF-PASS (a C baseline that drifts from the RTL is caught)")
    sys.exit(0)
print("BASELINE-MIRROR-PROOF-FAIL")
sys.exit(1)
