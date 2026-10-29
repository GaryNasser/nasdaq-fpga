"""Prove the constexpr guard fails if someone re-introduces Python evaluation."""
import io
import os
import shutil
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_constexpr.py")
GUARD = os.path.join(REPO, "tools", "check_constexpr_guard.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run_guard():
    r = subprocess.run([sys.executable, GUARD], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(GUARD))
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, out0 = run_guard()
print("baseline guard: exit=%d" % rc0)
if rc0 != 0:
    print("GUARD-PROOF-FAIL (the guard does not pass on the current tree)")
    sys.exit(1)

bk = CHK + ".bak"
shutil.copyfile(CHK, bk)
try:
    # Inject a Python re-implementation of the shift, the exact shape of the round-66 bug.
    src = io.open(CHK, encoding="utf-8", errors="surrogateescape").read()
    injected = src.replace(
        "EXPECT = [",
        "FIFO_BYTES_PY = 1 << (FIFO_AW if 'FIFO_AW' in dir() else 12)   # Python re-derivation\nEXPECT = [", 1)
    io.open(CHK, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(injected)
    print("injected a Python re-derivation into the checker")

    rc1, out1 = run_guard()
    caught = rc1 != 0
    print("mutated guard : exit=%d %s" % (rc1, "CAUGHT" if caught else "MISSED"))
    if not caught:
        for l in [x for x in out1.split("\n") if x.strip()][-3:]:
            print("   " + l.strip()[:78])
finally:
    shutil.copyfile(bk, CHK)
    os.unlink(bk)

rc2, _ = run_guard()
print("restored guard: exit=%d" % rc2)

print()
if caught and rc2 == 0:
    print("GUARD-PROOF-PASS (re-introducing Python evaluation is caught)")
    sys.exit(0)
print("GUARD-PROOF-FAIL (caught=%s restored=%s)" % (caught, rc2 == 0))
sys.exit(1)
