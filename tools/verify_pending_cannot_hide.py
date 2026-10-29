"""Verify the PENDING verdict cannot swallow a real failure.

Round 41 introduced exit code 75 so a tracked, hardware-pending gap does not read the
same as either a pass or a breakage. That adds a new way for the suite to stay green,
and every such mechanism in this project has eventually been shown able to hide
something:

    check_board_claims passed on zero matches
    check_warmup_advice passed on zero matches
    tb_parity2 could not fail
    five static checkers could not fail
    the simulation runner passed a token-then-fatal suite

So the PENDING path needs proving in both directions:

  1. a checker that exits 75 is recorded as PEND, NOT as a failure -> suite stays green
  2. a checker that exits 1 is recorded as FAIL                    -> suite goes red
  3. the summary line counts every row                            -> no silent drops

This runs run_checks with a deliberately broken check and confirms the suite fails. It
does so by pointing one CHECKS entry at a tiny script that always exits 1, then
restoring.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
RUN = os.path.join(TOOLS, "run_checks.py")

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(RUN, backup)
original = io.open(RUN, encoding="utf-8").read()

# Inject a checker that always fails, under an existing key so nothing else changes.
PROBE = os.path.join(TOOLS, "_probe_fail.py")
io.open(PROBE, "w", encoding="utf-8").write(
    '"""Deliberate failure used to prove the suite turns red."""\n'
    'import sys\n'
    'print("PROBE-FAIL")\n'
    'sys.exit(1)\n')

mutated = original.replace('    "utf8": "check_utf8.py",',
                           '    "utf8": "_probe_fail.py",', 1)
landed = mutated != original
io.open(RUN, "w", encoding="utf-8", newline="\n").write(mutated)

env = dict(os.environ)
env["PATH"] = r"D:\Xilinx\Vivado\2024.1\bin;" + env.get("PATH", "")
env["PYTHONIOENCODING"] = "utf-8"

r = subprocess.run([sys.executable, RUN], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env)
out = (r.stdout or "") + (r.stderr or "")

suite_failed = "SUITE-FAIL" in out
named = "utf8" in out.split("failed:")[-1] if "failed:" in out else False

print("probe injected : %s" % landed)
print("suite exit code: %d" % r.returncode)
print("SUITE-FAIL shown: %s" % suite_failed)
print("failing check named: %s" % named)
for line in out.strip().splitlines()[-4:]:
    print("  " + line)

shutil.copyfile(backup, RUN)
os.unlink(backup)
os.unlink(PROBE)
restored = io.open(RUN, encoding="utf-8").read() == original
print("restored: %s" % restored)

print()
if landed and suite_failed and r.returncode != 0 and named and restored:
    print("PENDING-CANNOT-HIDE-FAILURE-PASS")
else:
    print("PENDING-CANNOT-HIDE-FAILURE-FAIL")
    sys.exit(1)
