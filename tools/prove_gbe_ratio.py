"""Prove check_gbe_ratio fails when a ratio no longer follows from its figure.

Mutation: change 0.50x to 0.65x for the 63.0 MB/s figure. A stale ratio reads as a design claim
about performance relative to the wire, so a wrong one misstates the result.

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
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHK = os.path.join(REPO, "tools", "check_gbe_ratio.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Find the 63.0 MB/s ratio and corrupt it.
m = re.search(r"63\.0\s*MB/s（\*{0,2}([\d.]+)×\s*1\s*GbE", rep)
if not m:
    print("GBE-RATIO-PROOF-FAIL (63.0 MB/s ratio not found)")
    sys.exit(1)

print("the 63.0 MB/s ratio is stated as %sx" % m.group(1))
mutated = rep[:m.start(1)] + "0.65" + rep[m.end(1):]

results = []
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    results.append(("ratio 0.50 -> 0.65", caught))
    detail = next((l.strip() for l in out.splitlines() if "MISMATCH" in l), "")
    print("%-26s exit=%d %s  %s" % ("ratio 0.50 -> 0.65", rc,
                                    "CAUGHT" if caught else "MISSED", detail[:46]))
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("GBE-RATIO-PROOF-FAIL")
sys.exit(1)
