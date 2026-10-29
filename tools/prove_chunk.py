"""Prove both failure paths in check_chunk_fit.

Read from the source first:

    L21-L24  test_chunk_fit.py or chunk_sweep.py missing         -> CHUNK-FIT-FAIL, exit 1
    L32-L35  the test ran but printed FAIL or exited non-zero    -> CHUNK-FIT-FAIL, exit 1

The second is the one that matters: the wrapper trusts the inner test's own verdict, so a wrapper that merely
reported the inner test's stdout without checking the token would pass on a failing test.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_chunk_fit.py")
TEST = os.path.join(REPO, "tools", "test_chunk_fit.py")
SWEEP = os.path.join(REPO, "tools", "chunk_sweep.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=1200)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("CHUNK-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

results = []

# 1  The inner test fails.
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(TEST, bk)
try:
    io.open(TEST, "w", encoding="utf-8", newline="\n").write(
        'import sys\nprint("CHUNK-FIT-FAIL (stub)")\nsys.exit(1)\n')
    rc, _ = run()
    results.append(("inner test reports FAIL", rc != 0))
    print("  %-30s exit=%-3d %s" % ("inner test reports FAIL", rc, "CAUGHT" if rc else "MISSED"))
finally:
    shutil.copyfile(bk, TEST)
    os.unlink(bk)

# 2  The inner test exits 0 but prints FAIL (the sharper case: token and code disagree).
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(TEST, bk)
try:
    io.open(TEST, "w", encoding="utf-8", newline="\n").write(
        'import sys\nprint("CHUNK-FIT-FAIL (stub, exit 0)")\nsys.exit(0)\n')
    rc, _ = run()
    results.append(("FAIL token with exit 0", rc != 0))
    print("  %-30s exit=%-3d %s" % ("FAIL token with exit 0", rc, "CAUGHT" if rc else "MISSED"))
finally:
    shutil.copyfile(bk, TEST)
    os.unlink(bk)

# 3  A required file is absent.
bk2 = tempfile.mktemp(suffix=".py")
shutil.move(SWEEP, bk2)
try:
    rc, _ = run()
    results.append(("sweep script missing", rc != 0))
    print("  %-30s exit=%-3d %s" % ("sweep script missing", rc, "CAUGHT" if rc else "MISSED"))
finally:
    shutil.move(bk2, SWEEP)

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)

caught = sum(1 for _, c in results if c)
print()
if caught == len(results) and rc2 == 0:
    print("CHUNK-PROOF-PASS (%d/%d paths caught)" % (caught, len(results)))
    sys.exit(0)
print("CHUNK-PROOF-FAIL (%d of %d caught)" % (caught, len(results)))
sys.exit(1)
