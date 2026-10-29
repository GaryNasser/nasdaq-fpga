"""Prove check_crash_resilience catches a check that crashes instead of reporting.

Round 13 found three checks that died on a malformed report: two `next()` calls with no default and one
`bounds()` returning None. This puts the `next()` bug back into check_repro_args and requires the sweep to see it.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
TARGET = os.path.join(TOOLS, "check_repro_args.py")
SWEEP = os.path.join(TOOLS, "check_crash_resilience.py")

OLD = 'start = next((i for i, l in enumerate(lines) if l.startswith("## 9. \u590d\u73b0")), None)'
NEW = 'start = next(i for i, l in enumerate(lines) if l.startswith("## 9. \u590d\u73b0"))'


def run():
    r = subprocess.run([sys.executable, SWEEP], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS, timeout=1200)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "CRASH-RESILIENCE-PASS" if "CRASH-RESILIENCE-PASS" in out0 else "?"))
if rc0 != 0:
    print("CRASH-RESILIENCE-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(TARGET, encoding="utf-8").read()
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(TARGET, bk)
st = os.stat(TARGET)
try:
    mutated = orig.replace(OLD, NEW, 1)
    landed = mutated != orig
    io.open(TARGET, "w", encoding="utf-8", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0 and "CRASH" in out1
    print("reintroduce next() without default   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
    if landed and not caught:
        for l in out1.split("\n")[-4:]:
            if l.strip():
                print("   " + l.strip()[:78])
finally:
    shutil.copyfile(bk, TARGET)
    os.utime(TARGET, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("CRASH-RESILIENCE-PROOF-PASS (a check that dies on a broken report is caught)")
    sys.exit(0)
print("CRASH-RESILIENCE-PROOF-FAIL")
sys.exit(1)
