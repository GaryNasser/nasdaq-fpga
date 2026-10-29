"""Prove check_session_coverage fails when the report drops a regression reference.

Mutation: remove every mention of tb_false_sync from the report. The suite still runs that test;
the report no longer names it. Must fail.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHK = os.path.join(REPO, "tools", "check_session_coverage.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
if "tb_false_sync.v" not in rep:
    print("SESSION-COV-PROOF-FAIL (the report does not name tb_false_sync.v to begin with)")
    sys.exit(1)

mutated = rep.replace("tb_false_sync.v", "the rescan testbench")

results = []
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    results.append(("drop a testbench name", caught))
    detail = next((l.strip() for l in out.splitlines() if "never names it" in l), "")
    print("%-24s exit=%d %s  %s" % ("drop a testbench name", rc,
                                    "CAUGHT" if caught else "MISSED", detail[:44]))
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("SESSION-COV-PROOF-FAIL")
sys.exit(1)
