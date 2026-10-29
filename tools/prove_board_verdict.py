"""Prove check_board_verdict fails when the verdict is weakened.

The pre-fix verdict was `'GOLDEN-OK' in out` - a substring test, which returned success for a run
that printed GOLDEN-OK and then crashed. Two mutations restore that class of weakness:

    1  drop the clean_exit condition      -> a crash after GOLDEN-OK becomes success
    2  drop the saw_traceback condition   -> a traceback after GOLDEN-OK becomes success

Both must fail. This is the failure the project has been most wary of: declaring the design
verified at the one moment a false success costs a power cycle and a wasted trip.
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
DRV = os.path.join(TOOLS, "board_recover.py")
CHK = os.path.join(TOOLS, "check_board_verdict.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


src = io.open(DRV, encoding="utf-8").read()

CASES = [
    ("clean_exit condition dropped",
     src.replace("clean_exit = (returncode == 0)", "clean_exit = True", 1)),
    ("traceback condition dropped",
     src.replace("saw_traceback = 'Traceback (most recent call last)' in out",
                 "saw_traceback = False", 1)),
]

results = []
for label, mutated in CASES:
    if mutated == src:
        print("%-32s NOT APPLIED" % label)
        continue
    bk = tempfile.mktemp(suffix=".py")
    shutil.copyfile(DRV, bk)
    try:
        io.open(DRV, "w", encoding="utf-8", newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        results.append((label, caught))
        wrong = [l.strip() for l in out.splitlines() if "WRONG" in l]
        print("%-32s exit=%d %s  %s" % (label, rc, "CAUGHT" if caught else "MISSED",
                                        (wrong[0] if wrong else "")[:40]))
    finally:
        shutil.copyfile(bk, DRV)
        os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("BOARD-VERDICT-PROOF-FAIL")
sys.exit(1)
