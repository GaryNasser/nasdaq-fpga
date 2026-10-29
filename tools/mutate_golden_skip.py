"""Mutate the golden skip back to silent and confirm the check catches it.

An earlier attempt did this with a PowerShell one-liner and died on quote escaping,
so the "PASS" it printed tested nothing. This does the edit in Python and verifies
the mutation actually landed before running the check.
"""
import io
import subprocess
import sys
import os
import shutil
import tempfile

DRV = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_golden_paths.py"

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, backup)

# Round 253: interruption-safe restore. A killed run must not leave a source file modified.
import atexit as _atexit
_atexit.register(lambda _d=DRV, _b=backup: os.path.exists(_b) and shutil.copyfile(_b, _d))

src = io.open(DRV, encoding="utf-8", errors="surrogateescape").read()

# Find the failure block introduced in round 19 and replace its body with a
# silent success.
start = src.find("ref = _is_reference_capture(args.input, total_bytes)")
assert start != -1, "reference check not found"
ret = src.find("return 6", start)
assert ret != -1, "failure return not found"

mutated = (src[:start]
           + "print(\"GOLDEN-SKIPPED: mutated\")\n            return 0"
           + src[ret + len("return 6"):])

io.open(DRV, "w", encoding="utf-8", errors="surrogateescape",
        newline="\n").write(mutated)

# Verify the mutation actually changed the file.
after = io.open(DRV, encoding="utf-8", errors="surrogateescape").read()
mutation_landed = ("_is_reference_capture(args.input" not in after
                   and "GOLDEN-SKIPPED: mutated" in after)
print("mutation landed: %s" % mutation_landed)
if not mutation_landed:
    shutil.copyfile(backup, DRV)
    os.unlink(backup)
    sys.exit(2)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("check exit code: %d" % r.returncode)
tail = (r.stdout or "").strip().splitlines()[-3:]
for line in tail:
    print("  " + line)

shutil.copyfile(backup, DRV)
os.unlink(backup)

print()
if r.returncode == 0:
    print("MUTATION-NOT-CAUGHT: the check passed on a silent skip")
    sys.exit(1)
print("MUTATION-CAUGHT: the check fails when the skip goes silent")
