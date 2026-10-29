"""Prove check_ts_regmap fails when the driver's offset for a ts_hist register is wrong."""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_ts_regmap.py")
DRV = os.path.join(REPO, "board", "load_overlay.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("TS-REGMAP-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(DRV, encoding="utf-8", errors="surrogateescape").read()
m = re.search(r"(REG_TS_DELTA\s*=\s*)0x([0-9A-Fa-f]+)", body)
if not m:
    print("TS-REGMAP-PROOF-INCONCLUSIVE (REG_TS_DELTA not found)")
    sys.exit(0)

old = int(m.group(2), 16)
new = old + 4
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, bk)
try:
    io.open(DRV, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(
        body[:m.start(2)] + ("%X" % new) + body[m.end(2):])
    print("REG_TS_DELTA: 0x%02X -> 0x%02X" % (old, new))
    rc1, out1 = run()
    caught = rc1 != 0
    named = "DELTA" in out1
    print("mutated : exit=%d %s%s" % (rc1, "CAUGHT" if caught else "MISSED",
                                      "" if named else "  (but does not name it)"))
finally:
    shutil.copyfile(bk, DRV)
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if caught and named and rc2 == 0:
    print("TS-REGMAP-PROOF-PASS (a driver offset that disagrees with the RTL is caught and named)")
    sys.exit(0)
print("TS-REGMAP-PROOF-FAIL (caught=%s named=%s restored=%s)" % (caught, named, rc2 == 0))
sys.exit(1)
