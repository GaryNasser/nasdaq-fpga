"""Prove check_book_width catches a register narrower than the driver's 32-bit read."""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
RTL = r"D:\agent\nasdaq-fpga\rtl\itch\order_book.v"
CHECK = os.path.join(TOOLS, "check_book_width.py")

OLD = "reg [31:0]            drop_cnt;"
NEW = "reg [15:0]            drop_cnt;"


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "BOOK-WIDTH-PASS" if "BOOK-WIDTH-PASS" in out0 else "?"))
if rc0 != 0:
    print("BOOK-WIDTH-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(RTL, encoding="utf-8", errors="replace").read()
bk = tempfile.mktemp(suffix=".v")
shutil.copyfile(RTL, bk)
st = os.stat(RTL)
try:
    d = re.search(r"reg \[[^\]]+\]\s+drop_cnt\s*;", orig)
    landed = d is not None
    mutated = orig[:d.start()] + "reg [15:0]            drop_cnt;" + orig[d.end():] if landed else orig
    io.open(RTL, "w", encoding="utf-8", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0 and "BOOK-WIDTH-FAIL" in out1
    print("narrow drop_cnt to 16 bits   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
    if caught:
        for l in out1.split("\n"):
            if "DROP_CNT" in l:
                print("   " + l.strip()[:76])
                break
finally:
    shutil.copyfile(bk, RTL)
    os.utime(RTL, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("BOOK-WIDTH-PROOF-PASS (a narrow register is caught and named)")
    sys.exit(0)
print("BOOK-WIDTH-PROOF-FAIL")
sys.exit(1)
