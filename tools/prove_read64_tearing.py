"""Prove check_read64_tearing catches a 64-bit read taken while the counters are moving."""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
DRV = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
CHECK = os.path.join(TOOLS, "check_read64_tearing.py")

# Insert a bare read64 immediately after the DMA starts, before any sleep or drain.
ANCHOR = "    time.sleep(0.2)   # let the last event drain through the book FSM"
INJECT = ("    risky_rx = read64(m64_mmio, REG_M64_RX_PACKETS_LO, REG_M64_RX_PACKETS_HI)\n"
          + ANCHOR)


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "READ64-TEARING-PASS" if "READ64-TEARING-PASS" in out0 else "?"))
if rc0 != 0:
    print("READ64-TEARING-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(DRV, encoding="utf-8").read()
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, bk)
st = os.stat(DRV)
try:
    landed = ANCHOR in orig
    mutated = orig.replace(ANCHOR, INJECT, 1) if landed else orig
    io.open(DRV, "w", encoding="utf-8", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0 and "READ64-TEARING-FAIL" in out1
    print("inject an early read64   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, DRV)
    os.utime(DRV, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("READ64-TEARING-PROOF-PASS (an unquiesced 64-bit read is caught)")
    sys.exit(0)
print("READ64-TEARING-PROOF-FAIL")
sys.exit(1)
