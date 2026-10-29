"""Prove check_baseline_trace fails when the quoted figure is not the file's best.

Three mutations:

    1  report quotes 935.37 (the third run) instead of 927.35 (the best)
    2  report quotes a rate that does not match the best run
    3  the file loses a run, so "best of 4" is no longer true

Each must fail. A check that reads the file but compares against a remembered 927.35 would pass
all three.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
BASE = os.path.join(REPO, "docs", "measurements", "baseline-a9.txt")
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHK = os.path.join(REPO, "tools", "check_baseline_trace.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
base = io.open(BASE, encoding="latin-1").read()

CASES = []

# Target the BASELINE sentence. The first "ns/消息" in the document is the SIMULATED 299.01,
# so a pattern that matches it mutates the wrong chain. The baseline appears as
# "（927.35 ns，4 次取最优）" or "927.35 ns/消息".
m = re.search(r"（(927\.\d+) ns，4 次取最优）|(927\.\d+) ns/消息", rep)
if m:
    g = m.group(1) or m.group(2)
    CASES.append(("report quotes 935.37 not 927.35", REPORT,
                  rep.replace(g, "935.37"), "utf-8", "surrogateescape"))

m = re.search(r"即\s*([\d,]+)\s*消息/秒", rep)
if m:
    CASES.append(("rate 1,078,347 -> 1,200,000", REPORT,
                  rep[:m.start(1)] + "1,200,000" + rep[m.end(1):],
                  "utf-8", "surrogateescape"))

# Drop the best run from the file.
lines = base.split("\n")
idx = next((i for i, l in enumerate(lines) if "ns_per_msg=927.35" in l), None)
if idx is not None:
    CASES.append(("best run removed from the file", BASE,
                  "\n".join(lines[:idx] + lines[idx + 1:]), "latin-1", "replace"))

results = []
for label, path, mutated, enc, err in CASES:
    orig = io.open(path, encoding=enc, errors=err).read()
    if mutated == orig:
        print("%-38s NOT APPLIED" % label)
        continue
    bk = tempfile.mktemp(suffix=os.path.splitext(path)[1])
    shutil.copyfile(path, bk)
    try:
        io.open(path, "w", encoding=enc, errors=err, newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        results.append((label, caught))
        detail = next((l.strip() for l in out.splitlines() if "FAIL" in l or "!=" in l), "")
        print("%-38s exit=%d %s  %s" % (label, rc, "CAUGHT" if caught else "MISSED",
                                        detail[:40]))
    finally:
        shutil.copyfile(bk, path)
        os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("BASELINE-TRACE-PROOF-FAIL")
sys.exit(1)
