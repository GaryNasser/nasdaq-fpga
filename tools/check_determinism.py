"""Is every check deterministic - same input, same verdict, twice in a row?

Round 26 withdrew a sweep because three identical runs gave 7, then 2, then 3 failures. **That is a property worth
knowing about every check, not just that one**: a verdict that changes between runs cannot support a claim either way.

This runs the whole suite three times and compares the per-check outcome. A check that flips is either racy (it edits
shared state) or depends on something outside the tree (a clock, mtime, the network).
"""
import io
import os
import re
import subprocess
import sys
import time

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RUNS = 3
results = []

for run_no in range(1, RUNS + 1):
    t0 = time.time()
    r = subprocess.run([sys.executable, "-u", os.path.join(TOOLS, "run_checks.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=TOOLS)
    out = (r.stdout or "") + (r.stderr or "")
    fails = set()
    for line in out.split("\n"):
        m = re.match(r"^\[FAIL\]\s+(\w+)", line.strip())
        if m:
            fails.add(m.group(1))
    summary = ""
    for line in out.split("\n"):
        if line.startswith("passed "):
            summary = line.strip()
    results.append((run_no, r.returncode, fails, summary, time.time() - t0))
    print("run %d: exit=%d  %s  (%.0f s)"
          % (run_no, r.returncode, summary or "(no summary)", time.time() - t0))
    if fails:
        print("   failing: %s" % ", ".join(sorted(fails)))

print()
sets = [f for _, _, f, _, _ in results]
all_fails = set().union(*sets)
union_stable = set.intersection(*sets) if sets else set()
flaky = all_fails - union_stable

if flaky:
    print("checks whose verdict changed between identical runs: %d" % len(flaky))
    for n in sorted(flaky):
        seen = ["FAIL" if n in s else "pass" for s in sets]
        print("  %-30s %s" % (n, " ".join(seen)))
    print()
    print("DETERMINISM-FAIL (%d check(s) are not reproducible)" % len(flaky))
    sys.exit(1)

print("DETERMINISM-PASS (three consecutive runs agree on every check's verdict)")
