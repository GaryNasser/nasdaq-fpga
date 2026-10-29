"""Prove check_carry_over fails when the carry-over notes are removed.

Mutation: delete every "同样存在于" sentence from the report, leaving the equivalence claims
standing alone. A reader would then conclude the RTL defects were introduced after the
measurement, which is the opposite of the truth.
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
CHK = os.path.join(REPO, "tools", "check_carry_over.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
if "同样存在于" not in rep:
    print("CARRY-OVER-PROOF-FAIL (no carry-over note to remove)")
    sys.exit(1)

# Remove the sentence carrying the note, then ASSERT the mutation landed: a mutation that leaves a
# matching fragment behind proves nothing. The first version of this proof removed single lines and
# left "一直在那里" glued to the previous line, so the check still passed.
NOTE = re.compile(r"同样存在于|一直在那里|缺陷.{0,20}带进")
lines = rep.split("\n")
mutated_lines = [l for l in lines if not NOTE.search(l)]
mutated = "\n".join(mutated_lines)
removed = len(lines) - len(mutated_lines)

if NOTE.search(mutated):
    print("CARRY-OVER-PROOF-FAIL (the mutation did not remove every carry-over fragment)")
    sys.exit(1)
if removed == 0:
    print("CARRY-OVER-PROOF-FAIL (nothing was removed)")
    sys.exit(1)

results = []
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    results.append(("remove carry-over notes", caught))
    detail = next((l.strip() for l in out.splitlines() if "without noting" in l), "")
    print("%-26s exit=%d %s  %s (%d line(s) removed)" % ("remove carry-over notes", rc,
                                                         "CAUGHT" if caught else "MISSED",
                                                         detail[:34], removed))
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("CARRY-OVER-PROOF-FAIL")
sys.exit(1)
