"""Prove check_capacity_edge fails when a capacity loses its boundary test.

Round 8: the sweep found ORDERS had no bench reaching its edge, while LEVELS did (round 7's
tb_book_levels). This removes the LEVELS bench's coverage by shrinking its instantiated table and
requires the sweep to notice.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
TARGET = os.path.join(TOOLS, "tb_book_levels.v")
SWEEP = os.path.join(TOOLS, "check_capacity_edge.py")

OLD = "        .LEVELS(LEVELS),"
NEW = "        .LEVELS(4),"


def run():
    r = subprocess.run([sys.executable, SWEEP], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "CAPACITY-EDGE-PASS" if "CAPACITY-EDGE-PASS" in out0 else "?"))
if rc0 != 0:
    print("CAPACITY-EDGE-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(TARGET, encoding="utf-8").read()
bk = tempfile.mktemp(suffix=".v")
shutil.copyfile(TARGET, bk)
st = os.stat(TARGET)
try:
    mutated = orig.replace(OLD, NEW, 1)
    landed = mutated != orig
    io.open(TARGET, "w", encoding="utf-8", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0 and "LEVELS" in out1
    print("shrink the LEVELS bench   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, TARGET)
    os.utime(TARGET, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("CAPACITY-EDGE-PROOF-PASS (a table whose edge is no longer reached is caught)")
    sys.exit(0)
print("CAPACITY-EDGE-PROOF-FAIL")
sys.exit(1)
