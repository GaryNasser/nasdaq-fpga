"""Prove check_regmap fails when the driver's register constant disagrees with the RTL.

With the board offline, `check_regmap` is the only thing standing between a driver bug and an unexplained wrong read
on hardware. **It has never been shown to fail.**

Mutate one register offset in `board/load_overlay.py` and confirm exit 1 naming it.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
DRV = os.path.join(REPO, "board", "load_overlay.py")
CHK = os.path.join(REPO, "tools", "check_regmap.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, out0 = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("REGMAP-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(DRV, encoding="utf-8", errors="surrogateescape").read()

# A driver register constant: REG_xxx = 0xNN
# Only registers the RTL actually implements: the M64 block. loopback_dma registers (M1) are not in
# the current design and have no RTL counterpart to disagree with.
m = re.search(r"(REG_M64_\w+\s*=\s*)0x([0-9A-Fa-f]+)", body)
if not m:
    print("REGMAP-PROOF-INCONCLUSIVE (no REG_ constant found in the driver)")
    sys.exit(0)

name = m.group(1).split("=")[0].strip()
old = int(m.group(2), 16)
new = old + 4
print("mutating %s: 0x%02X -> 0x%02X" % (name, old, new))

bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, bk)
try:
    mutated = body[:m.start(2)] + ("%X" % new) + body[m.end(2):]
    io.open(DRV, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0
    named = name in out1
    print("mutated : exit=%d %s%s" % (rc1, "CAUGHT" if caught else "MISSED",
                                      "" if named else "  (but does not name the register)"))
    if not caught:
        for l in [x for x in out1.split("\n") if x.strip()][-4:]:
            print("   " + l.strip()[:80])
finally:
    shutil.copyfile(bk, DRV)
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if caught and named and rc2 == 0:
    print("REGMAP-PROOF-PASS (a driver/RTL register mismatch is caught and named)")
    sys.exit(0)
print("REGMAP-PROOF-FAIL (caught=%s named=%s restored=%s)" % (caught, named, rc2 == 0))
sys.exit(1)
