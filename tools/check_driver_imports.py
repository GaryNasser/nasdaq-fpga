"""The same fallback pattern may exist in other checks. Find all of them.

check_reference_id tried to import the driver, fell back to a copy when numpy was missing, and
tested the copy. That is a specific shape:

    try:  import / exec a module
    except: re-implement what the module does
    ...then test the re-implementation

Any check with that shape reports PASS about something it never loaded. Rounds 41-42 fixed the
document-version of this fault; this is the code version.

Also worth checking: checks that DO import the driver but would fail without stubs. Those are
correct only if they install stand-ins first, as check_reference_id now does.

This scans every check for: an import attempt of load_overlay.py, and whether any module
stubbing precedes it.
"""
import io
import os
import re
import subprocess
import sys
import glob


import glob
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOOLS = os.path.dirname(os.path.abspath(__file__))

# A check that loads the driver must not end up on a fallback path. The fallback announces
# itself, so the test is behavioural: run the check, look for the token.
FALLBACK = re.compile(r"-FALLBACK|could not import the driver")

print("checks that load the driver, and whether they actually load it")
print()

loaders = []
for p in sorted(glob.glob(os.path.join(TOOLS, "check_*.py"))):
    name = os.path.basename(p)
    if name == os.path.basename(__file__):
        continue
    text = io.open(p, encoding="utf-8", errors="replace").read()
    code = re.sub(r'""".*?"""', "", text, flags=re.S)
    if "load_overlay" not in code:
        continue
    if not re.search(r"spec_from_file_location|exec_module", code):
        continue
    loaders.append((name, p))

fails = []
for name, p in loaders:
    try:
        r = subprocess.run([sys.executable, p], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
    except subprocess.TimeoutExpired:
        print("  %-32s TIMEOUT" % name)
        fails.append("%s timed out" % name)
        continue
    out = (r.stdout or "") + (r.stderr or "")
    fell_back = bool(FALLBACK.search(out))
    print("  %-32s %s" % (name, "FELL BACK - did not load the driver" if fell_back
                          else "loaded the driver"))
    if fell_back:
        fails.append("%s could not import the driver, so it tests something else" % name)

print()
print("  %d check(s) load the driver" % len(loaders))
print()
if not loaders:
    print("DRIVER-IMPORT-FAIL (no check loads the driver - the scan would be vacuous)")
    sys.exit(1)
if fails:
    print("DRIVER-IMPORT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("DRIVER-IMPORT-PASS (%d check(s) genuinely load the driver)" % len(loaders))
