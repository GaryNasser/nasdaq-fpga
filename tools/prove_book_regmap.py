"""Prove check_book_regmap catches a driver offset that drifts from the RTL.

Round 20: order_book had 13 register addresses and NO check tying them to the driver's BOOK_REGS. This shifts
one and requires the check to notice.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
DRV = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
CHECK = os.path.join(TOOLS, "check_book_regmap.py")

OLD = "'drop_cnt': 0x2C,"
NEW = "'drop_cnt': 0x30,"


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "BOOK-REGMAP-PASS" if "BOOK-REGMAP-PASS" in out0 else "?"))
if rc0 != 0:
    print("BOOK-REGMAP-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(DRV, encoding="utf-8").read()
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, bk)
st = os.stat(DRV)
try:
    mutated = orig.replace(OLD, NEW, 1)
    landed = mutated != orig
    io.open(DRV, "w", encoding="utf-8", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0 and "BOOK-REGMAP-FAIL" in out1
    print("shift drop_cnt to 0x30   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, DRV)
    os.utime(DRV, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("BOOK-REGMAP-PROOF-PASS (a driver offset that drifts from the RTL is caught)")
    sys.exit(0)
print("BOOK-REGMAP-PROOF-FAIL")
sys.exit(1)
