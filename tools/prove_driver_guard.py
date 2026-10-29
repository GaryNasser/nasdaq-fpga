"""Does check_driver_imports catch a check that stops stubbing?

The guard prints checks that load the driver without stand-ins, but printing is not failing.
If it does not fold that into its verdict, removing the stub would be reported and still PASS.

Test: disable the stub in check_reference_id, run the guard, require a non-zero exit. Then
restore and require zero.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
REF = os.path.join(TOOLS, "check_reference_id.py")
GUARD = os.path.join(TOOLS, "check_driver_imports.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, GUARD], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("healthy: exit=%d" % rc0)
print()

src = io.open(REF, encoding="utf-8").read()
if "MOCKPATH = _install_stubs()" not in src:
    print("PROOF-FAIL (stub call not found)")
    sys.exit(1)

mutated = src.replace("MOCKPATH = _install_stubs()",
                      "MOCKPATH = None   # MUTATION: no stand-ins", 1)

bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(REF, bk)
try:
    io.open(REF, "w", encoding="utf-8", newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    print("with the stub removed:")
    for l in out.splitlines():
        if l.strip():
            print("   %s" % l.strip()[:86])
    print("   exit=%d %s" % (rc, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, REF)
    os.unlink(bk)

rc2, out2 = run()
print()
print("restored: exit=%d" % rc2)

if caught and rc2 == 0:
    sys.exit(0)

# If the guard only prints, say so precisely.
print()
print("the guard reports the fact but does not fail on it:")
print("  a check that stops stubbing would be listed and the suite would still pass.")
sys.exit(1)
