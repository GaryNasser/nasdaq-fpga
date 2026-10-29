"""Prove check_skip_conversion fails when a report-guarded checker does NOT react to the report's absence.

`check_skip_conversion` moves the report away and requires 11 named checkers to exit non-zero. **It is itself a
validation** - but nothing validates IT. If its detection is wrong, it reports PASS while some guard has silently
reverted to exit 0.

Substitute one of the 11 checkers with a stub that exits 0 unconditionally, then confirm skip_conversion fails.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_skip_conversion.py")
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VICTIM = os.path.join(TOOLS, "check_t1_sets.py")

if not os.path.exists(VICTIM):
    print("SKIP-CONVERSION-PROOF-FAIL (victim not found)")
    sys.exit(1)


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=TOOLS, timeout=1200)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, out0 = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("SKIP-CONVERSION-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(VICTIM, bk)
try:
    # A stub that always succeeds: the exact regression the check exists to catch.
    io.open(VICTIM, "w", encoding="utf-8", newline="\n").write(
        '"""Stub: always succeeds, so an absent report no longer causes a failure."""\n'
        'import sys\n'
        'print("T1-SETS-PASS (stub)")\n'
        'sys.exit(0)\n')
    print("replaced check_t1_sets.py with an always-passing stub")

    rc1, out1 = run()
    caught = rc1 != 0
    named = "check_t1_sets" in out1
    print("mutated : exit=%d %s%s" % (rc1, "CAUGHT" if caught else "MISSED",
                                      "" if named else "  (but does not name it)"))
    if not caught:
        for l in [x for x in out1.split("\n") if x.strip()][-4:]:
            print("   " + l.strip()[:80])
finally:
    shutil.copyfile(bk, VICTIM)
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if caught and named and rc2 == 0:
    print("SKIP-CONVERSION-PROOF-PASS (a reverted guard is caught and named)")
    sys.exit(0)
print("SKIP-CONVERSION-PROOF-FAIL (caught=%s named=%s restored=%s)" % (caught, named, rc2 == 0))
sys.exit(1)
