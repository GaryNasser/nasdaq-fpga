"""One more retry for reference_id, and a documented gap for transfer_reset.

reference_id: the predicate is

    if total_bytes != REFERENCE_CAPTURE_SIZE: return False
    head = f.read(1024)
    return sha256(head)[:16] == REFERENCE_HEAD_SHA256_16

The third test - "same size, zeroed content must be False" - exercises the HASH, not the size.
My earlier edits changed the size test, which the third case never reaches. The mutation must
neutralise the hash comparison.

transfer_reset: the rule is "the nearest CTRL write is one of the expected values". Deleting
the 0x2 reset leaves 0x1, which is expected, so it passes. Its own docstring says a PL
transfer "requires a preceding CTRL write" - not a preceding RESET. So the check is weaker
than the name suggests, and that is a finding rather than a mutation error.

Both outcomes are worth recording: one proves the check works, the other shows its limit.
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

drv = io.open(DRV, encoding="utf-8", errors="replace").read()

# Neutralise the hash comparison so any same-size file passes.
OLD = ("return hashlib.sha256(head).hexdigest()[:16] == REFERENCE_HEAD_SHA256_16")
NEW = "return True   # MUTATION: content no longer checked"

if OLD not in drv:
    print("REFERENCE-ID-MUTATION-FAIL (hash line not found)")
    sys.exit(1)

mutated = drv.replace(OLD, NEW, 1)
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, bk)
try:
    io.open(DRV, "w", encoding="utf-8", errors="replace", newline="\n").write(mutated)
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "check_reference_id.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    caught = r.returncode != 0
    print("reference_id, hash comparison neutralised:")
    for l in out.splitlines()[-6:]:
        if l.strip():
            print("   %s" % l.strip()[:88])
    print("   exit=%d %s" % (r.returncode, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, DRV)
    os.unlink(bk)

r = subprocess.run([sys.executable, os.path.join(TOOLS, "check_reference_id.py")],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print("   restored exit=%d" % r.returncode)

print()
print("transfer_reset: the gap, stated plainly")
print()
print("  its rule is 'the nearest CTRL write is one of the expected values'.")
print("  Deleting the reset (0x2) from the --book path leaves 0x1 nearby and still passes.")
print("  A PL transfer that enables WITHOUT resetting is the defect in its name, and it")
print("  does not fail on it. Recorded as a known limitation rather than a proof.")

# The mutation cannot be caught while the driver is unimportable: the check tests its own
# copy of the predicate, so editing the driver changes nothing it evaluates. That is the
# finding, not a failure of this harness - and a harness that always fails would break the
# suite for a reason unrelated to the mutation.
#
# This script therefore reports the fact and exits 0 only when the restore succeeded. It is
# NOT registered as proof that check_reference_id can fail; it documents that it cannot be
# shown to, on this machine.
print()
print("REFERENCE-ID-MUTATION-UNPROVABLE (the check tests its own copy; the driver is not")
print("importable without numpy, so no driver edit can reach it)")
if r.returncode == 0:
    sys.exit(0)
sys.exit(1)
