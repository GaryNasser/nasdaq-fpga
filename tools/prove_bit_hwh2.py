"""bit_hwh compares <SYSTEMINFO DEVICE="7z020"> against 7z020 in the bitstream header.

The mutation: change the hwh's DEVICE to 7z035. The check should fail with
"bit part 7z020 vs hwh device 7z035".

Third attempt at this mutation, for the same reason as every previous one: I guessed the field
before reading the rule. The check's own lines 45 and 52-55 name it exactly.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
HWH = os.path.join(REPO, "vivado", "out", "nasdaq.hwh")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "check_bit_hwh.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


raw = io.open(HWH, encoding="latin-1").read()
pat = re.compile(r'(<SYSTEMINFO[^>]*DEVICE=")([^"]+)(")')
m = pat.search(raw)
if not m:
    print("BIT-HWH-PROOF-FAIL (DEVICE attribute not found)")
    sys.exit(1)

print("current DEVICE: %s -> 7z035" % m.group(2))

mutated = raw[:m.start(2)] + "7z035" + raw[m.end(2):]
bk = tempfile.mktemp(suffix=".hwh")
shutil.copyfile(HWH, bk)
try:
    io.open(HWH, "w", encoding="latin-1", newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    for l in out.splitlines():
        if "part" in l or "device" in l or "FAIL" in l:
            print("   %s" % l.strip()[:88])
    print("   exit=%d %s" % (rc, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, HWH)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)

if caught and rc2 == 0:
    sys.exit(0)
print("BIT-HWH-PROOF-FAIL")
sys.exit(1)
