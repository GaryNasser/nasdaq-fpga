"""Confirm the return audit catches the round-19 defect if it comes back.

Round 19 changed this:

    if nmsg != 43428:
        ...FAIL-ASSERT..., return 6

back from a silent `return 0`. If that regressed, the audit must notice. This
reintroduces the silent return, verifies the mutation landed, and runs the audit.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

DRV = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
AUDIT = r"D:\agent\nasdaq-fpga\tools\audit_returns.py"

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, backup)

# Round 253: interruption-safe restore. A killed run must not leave a source file modified.
import atexit as _atexit
_atexit.register(lambda _d=DRV, _b=backup: os.path.exists(_b) and shutil.copyfile(_b, _d))

src = io.open(DRV, encoding="utf-8", errors="surrogateescape").read()

# Replace the failure return in the reference-capture branch with a silent skip.
target = "FAIL-ASSERT: parsed {nmsg} messages from the reference"
i = src.find(target)
assert i != -1, "reference-capture failure message not found"
ret = src.find("return 6", i)
assert ret != -1, "return 6 not found"

mutated = src[:i] + "print(f\"count wrong: {nmsg}\")\n            return 0" \
    + src[src.find("\n", src.find("return 6", i)):]

io.open(DRV, "w", encoding="utf-8", errors="surrogateescape",
        newline="\n").write(mutated)

after = io.open(DRV, encoding="utf-8", errors="surrogateescape").read()
landed = ("FAIL-ASSERT: parsed {nmsg} messages from the reference" not in after
          and "count wrong" in after)
print("mutation landed: %s" % landed)

r = subprocess.run([sys.executable, AUDIT], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("audit exit code: %d" % r.returncode)
for line in (r.stdout or "").strip().splitlines()[-4:]:
    print("  " + line)

shutil.copyfile(backup, DRV)
os.unlink(backup)

print()
if not landed:
    print("MUTATION-DID-NOT-APPLY")
    sys.exit(2)
if r.returncode == 0:
    print("MUTATION-NOT-CAUGHT")
    sys.exit(1)
print("MUTATION-CAUGHT")
