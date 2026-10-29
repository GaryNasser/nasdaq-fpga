"""Prove check_dead_tb fails when a hanging testbench is shown as passing without a caveat.

Mutation: revert section 3's row to its pre-round-130 form, which asserts TB-ALL-PASS with only
"已废弃，会挂起" in the location column - no statement that the result is unreproducible.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHK = os.path.join(REPO, "tools", "check_dead_tb.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Replace the corrected row with one whose PASS carries no unreproducible caveat.
import re
m = re.search(r"\| `tb_mold64_reasm` \|[^\n]*\n", rep)
if not m:
    print("DEAD-TB-PROOF-FAIL (row not found)")
    sys.exit(1)

mutated_row = "| `tb_mold64_reasm` | `TB-ALL-PASS` | `rtl/itch/`（已废弃） |\n"
mutated = rep[:m.start()] + mutated_row + rep[m.end():]

results = []
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    results.append(("PASS without a caveat", caught))
    detail = next((l.strip() for l in out.splitlines() if "PROBLEM" in l), "")
    print("%-26s exit=%d %s  %s" % ("PASS without a caveat", rc,
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
print("DEAD-TB-PROOF-FAIL")
sys.exit(1)
