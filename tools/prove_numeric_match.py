"""Prove check_numeric_match fails when a check accepts a substring.

Round 4: four figures in check_figure_derive and two counts in audit_numbers were matched with a plain `in`.
This restores that behaviour in ONE of them and requires the sweep to catch it.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
TARGET = os.path.join(TOOLS, "check_figure_derive.py")
SWEEP = os.path.join(TOOLS, "check_numeric_match.py")

OLD = 'present = re.search(r"(?<![\\d.])" + re.escape(value) + r"(?![\\d])", text) is not None'
NEW = "present = value in text"


def run():
    r = subprocess.run([sys.executable, SWEEP], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "NUMERIC-MATCH-PASS" if "NUMERIC-MATCH-PASS" in out0 else "?"))
if rc0 != 0:
    print("NUMERIC-MATCH-PROOF-FAIL (control does not pass)")
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
    caught = rc1 != 0
    print("restored substring match  landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, TARGET)
    os.utime(TARGET, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("NUMERIC-MATCH-PROOF-PASS (a check that accepts a substring is caught)")
    sys.exit(0)
print("NUMERIC-MATCH-PROOF-FAIL (landed=%s caught=%s restored=%s)" % (landed, caught, rc2 == 0))
sys.exit(1)
