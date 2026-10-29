"""Prove check_sim_coverage fails when a built module is absent from the simulation.

Mutation: remove ts_hist.v from the simulation's CHAIN list, so the build includes a module the
simulation never compiles. The suite would still show 15/15 - the chain tests would use whatever
modules remain - and nothing would say that ts_hist is unexercised.

Must fail.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
SIMS = os.path.join(REPO, "tools", "run_sims.py")
CHK = os.path.join(REPO, "tools", "check_sim_coverage.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


src = io.open(SIMS, encoding="utf-8").read()

# Remove ts_hist.v from every list the simulation compiles.
mutated = re.sub(r',?\s*os\.path\.join\(RTL,\s*"ts_hist\.v"\)', "", src)
if mutated == src:
    print("SIM-COVERAGE-PROOF-FAIL (ts_hist.v reference not found)")
    sys.exit(1)

results = []
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(SIMS, bk)
try:
    io.open(SIMS, "w", encoding="utf-8", newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    results.append(("ts_hist dropped from the sims", caught))
    detail = next((l.strip() for l in out.splitlines() if "built but not" in l), "")
    print("%-32s exit=%d %s  %s" % ("ts_hist dropped from the sims", rc,
                                    "CAUGHT" if caught else "MISSED", detail[:40]))
finally:
    shutil.copyfile(bk, SIMS)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("SIM-COVERAGE-PROOF-FAIL")
sys.exit(1)
