"""Prove check_timing_arith fails on a wrong margin and on a claimed 200 MHz closure.

    1  change the 2.4% margin to 4.8% (a plausible-looking but wrong division)
    2  insert a sentence claiming the design closes at 200 MHz

Both must fail: the first because the percentage no longer follows from the slack, the second
because the stated slack and the period difference say it does not.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHK = os.path.join(REPO, "tools", "check_timing_arith.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

CASES = []

m = re.search(r"\+0\.126\s*ns\*{0,2}[（(]\*{0,2}([\d.]+)\s*%", rep)
if m:
    CASES.append(("margin 2.4% -> 4.8%",
                  rep[:m.start(1)] + "4.8" + rep[m.end(1):]))

CASES.append(("claims closure at 200 MHz",
              rep + "\n\n本设计在 200 MHz 下同样可以收敛闭合。\n"))

results = []
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    for label, mutated in CASES:
        if mutated == rep:
            print("%-30s NOT APPLIED" % label)
            continue
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
                newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        results.append((label, caught))
        detail = next((l.strip() for l in out.splitlines()
                       if "MISMATCH" in l or "TIMING-ARITH-FAIL" in l
                       or "claims closure" in l), "")
        print("%-30s exit=%d %s  %s" % (label, rc, "CAUGHT" if caught else "MISSED",
                                        detail[:38]))
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("TIMING-ARITH-PROOF-FAIL")
sys.exit(1)
