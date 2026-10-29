"""Prove check_log_linkage fails when a check is added with no log entry.

Round 23: rounds 14-22 were never recorded, and 25 primary checks predated the rule. The check is forward-only -
this registers a fictional check name in the runner and requires the sweep to reject it.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
RUNNER = os.path.join(TOOLS, "run_checks.py")
CHECK = os.path.join(TOOLS, "check_log_linkage.py")

FAKE = ("zz_unlogged_probe", "a fictional check added without a log entry", False)


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "LOG-LINKAGE-PASS" if "LOG-LINKAGE-PASS" in out0 else "?"))
if rc0 != 0:
    print("LOG-LINKAGE-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(RUNNER, encoding="utf-8").read()
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(RUNNER, bk)
st = os.stat(RUNNER)
try:
    last_check = re.findall(r'^\s*\("\w+",[^\n]*\n', orig, re.M)[-1].rstrip("\n")
    injected = orig.replace(
        last_check,
        last_check + '\n    ("%s", "%s", False),' % (FAKE[0], FAKE[1]),
        1)
    landed = injected != orig
    io.open(RUNNER, "w", encoding="utf-8", newline="\n").write(injected)
    rc1, out1 = run()
    caught = rc1 != 0 and "LOG-LINKAGE-FAIL" in out1 and FAKE[0] in out1
    print("add an unlogged check   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, RUNNER)
    os.utime(RUNNER, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("LOG-LINKAGE-PROOF-PASS (a new check with no log entry is rejected)")
    sys.exit(0)
print("LOG-LINKAGE-PROOF-FAIL")
sys.exit(1)
