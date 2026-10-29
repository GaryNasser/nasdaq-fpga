"""Prove check_registry fails on both kinds of mismatch."""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_registry.py")
RUNNER = os.path.join(REPO, "tools", "run_checks.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("REGISTRY-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(RUNNER, encoding="utf-8").read()
results = []


def inject(label, transform, expect_fail):
    mutated = transform(body)
    if mutated == body:
        print("  %-42s INCONCLUSIVE" % label)
        return None
    bk = tempfile.mktemp(suffix=".py")
    shutil.copyfile(RUNNER, bk)
    try:
        io.open(RUNNER, "w", encoding="utf-8", newline="\n").write(mutated)
        rc, _ = run()
    finally:
        shutil.copyfile(bk, RUNNER)
        os.unlink(bk)
    failed = rc != 0
    ok = (failed == expect_fail)
    print("  %-42s exit=%-3d %s" % (label, rc, "ok" if ok else "*** WRONG ***"))
    return ok


# 1  orphan mapping: a SCRIPT entry with no CHECKS row (exactly what round 248 removed)
r1 = inject("orphan SCRIPT entry added",
            lambda b: b.replace('CHECKS = [', 'CHECKS = [', 1).replace(
                '"latches": "check_latches.py",',
                '"latches": "check_latches.py",\n    "zz_orphan": "check_latches.py",', 1),
            True)

# 2  a check with no mapping
r2 = inject("CHECKS row with no SCRIPT entry",
            lambda b: b.replace('    ("latches",', '    ("zz_nomap", "no script for this", False),\n    ("latches",', 1),
            True)

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)

oks = [x for x in (r1, r2) if x is not None]
print()
if oks and all(oks) and rc2 == 0:
    print("REGISTRY-PROOF-PASS (%d/%d mismatch kinds caught)" % (len(oks), len(oks)))
    sys.exit(0)
print("REGISTRY-PROOF-FAIL")
sys.exit(1)
