"""Now that the driver really loads, does editing it change check_reference_id's verdict?

Round 87 established the check was testing its own copy. The stub was added this round and the
output changed from PASS-UNVERIFIED to PASS, which means the driver imported.

The test that matters: neutralise the driver's hash comparison (so any same-size file passes)
and require the "same size, zeroed content" case to FAIL.

If it still passes, the fallback is still being used and the stub did not take effect - the
PASS token alone would not distinguish those two, which is why the mutation is the real test.
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
DRV = os.path.join(REPO, "board", "load_overlay.py")
CHK = os.path.join(TOOLS, "check_reference_id.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


drv = io.open(DRV, encoding="utf-8", errors="replace").read()

OLD = "return hashlib.sha256(head).hexdigest()[:16] == REFERENCE_HEAD_SHA256_16"
if OLD not in drv:
    print("REFERENCE-ID-PROOF-FAIL (hash line not found)")
    sys.exit(1)

mutated = drv.replace(OLD, "return True   # MUTATION", 1)

bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, bk)
try:
    io.open(DRV, "w", encoding="utf-8", errors="replace", newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    print("driver's hash comparison neutralised:")
    for l in out.splitlines():
        if l.strip():
            print("   %s" % l.strip()[:90])
    print("   exit=%d %s" % (rc, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, DRV)
    os.unlink(bk)

rc2, out2 = run()
print()
print("restored exit=%d" % rc2)
print("  token: %s" % [l for l in out2.splitlines() if "PASS" in l or "FAIL" in l][-1:])

if caught and rc2 == 0:
    sys.exit(0)
print("REFERENCE-ID-PROOF-FAIL")
sys.exit(1)
