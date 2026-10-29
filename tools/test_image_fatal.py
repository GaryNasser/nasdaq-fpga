"""Confirm a missing dataset stops the suite with a named cause.

Round 68 fixed the data recipe; this makes a missing dataset fail immediately rather than
producing three confusing suite failures.

Test: temporarily rename data/itch_loc6836.mold64, run the suite, and require:
  * a non-zero exit,
  * "SIMSUITE-FAIL (no test image)" printed,
  * the message naming data/itch_loc6836.mold64 as missing.

Then restore and require the suite to pass again.

This is a slow test (a full simulation run) so it is not part of the default suite; it is
run by hand when the image-generation path changes.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
DATA = os.path.join(REPO, "data", "itch_loc6836.mold64")
RUNNER = os.path.join(REPO, "tools", "run_sims.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(DATA):
    print("IMAGE-FATAL-SKIPPED (no capture to hide)")
    sys.exit(0)

backup = tempfile.mktemp(suffix=".mold64")
shutil.copyfile(DATA, backup)
original = open(DATA, "rb").read()

env = dict(os.environ)
env["PATH"] = r"D:\Xilinx\Vivado\2024.1\bin;" + env.get("PATH", "")
env["PYTHONIOENCODING"] = "utf-8"

print("hiding data/itch_loc6836.mold64 and running the suite")
print()
try:
    os.remove(DATA)
    r = subprocess.run([sys.executable, RUNNER], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=1800)
    out = (r.stdout or "") + (r.stderr or "")
finally:
    open(DATA, "wb").write(original)
    os.unlink(backup)

restored = open(DATA, "rb").read() == original

named = "SIMSUITE-FAIL (no test image)" in out
says_missing = "data/itch_loc6836.mold64 is missing" in out
points_to_section = "section 9.2" in out

print("  exit code            : %d" % r.returncode)
print("  SIMSUITE-FAIL token  : %s" % named)
print("  names the data file  : %s" % says_missing)
print("  points to section 9.2: %s" % points_to_section)
print("  restored             : %s" % restored)

# Show the decisive lines.
print()
print("  relevant output:")
for line in out.splitlines():
    if any(k in line for k in ("no test image", "is missing", "section 9.2",
                               "img.hex")):
        print("     " + line.strip()[:96])

print()
if r.returncode != 0 and named and says_missing and restored:
    print("IMAGE-FATAL-PASS")
else:
    print("IMAGE-FATAL-FAIL")
    sys.exit(1)
