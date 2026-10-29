"""Prove check_addr_plane catches two registers colliding on one offset."""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
RTL = r"D:\agent\nasdaq-fpga\rtl\itch\ts_hist.v"
CHECK = os.path.join(TOOLS, "check_addr_plane.py")


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "ADDR-PLANE-PASS" if "ADDR-PLANE-PASS" in out0 else "?"))
if rc0 != 0:
    print("ADDR-PLANE-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(RTL, encoding="utf-8", errors="replace").read()
bk = tempfile.mktemp(suffix=".v")
shutil.copyfile(RTL, bk)
st = os.stat(RTL)
try:
    m = re.search(r"localparam \[[^\]]+\] ADDR_(\w+)\s*=\s*\d+'d(\d+);", orig)
    landed = m is not None
    # Move the first register onto the second one's index, keeping the comment honest so the
    # collision is what fails rather than the comment.
    mutated = (orig[:m.start()] + "localparam [9:0] ADDR_%s = 10'd1;" % m.group(1)
               + orig[m.end():]) if landed else orig
    io.open(RTL, "w", encoding="utf-8", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0 and "ADDR-PLANE-FAIL" in out1
    print("collide %s onto index 1   landed=%s exit=%d %s"
          % (m.group(1) if m else "?", landed, rc1, "CAUGHT" if caught else "MISSED"))
    if caught:
        for l in out1.split("\n"):
            if "collide" in l:
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
    print("ADDR-PLANE-PROOF-PASS (a register collision is caught and named)")
    sys.exit(0)
print("ADDR-PLANE-PROOF-FAIL")
sys.exit(1)
