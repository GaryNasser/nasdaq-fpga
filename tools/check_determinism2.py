"""Re-run the determinism test with nothing else touching the tree.

The first attempt reported six non-deterministic checks - but it ran while I was ALSO regenerating `docs/status.md`
and editing the report, so `status_genuine`, `status_proof`, `summary_provenance` and `mutate_summary_prov_proof`
were seeing my edits, not a defect.

**A determinism test is only valid if its own environment is quiet.** This version refuses to start if the working
tree has uncommitted changes, and records the git hash so the runs are provably identical apart from time.
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

st = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", cwd=REPO)
if st.stdout.strip():
    print("DETERMINISM-INCONCLUSIVE: the tree is dirty, so runs are not identical")
    for l in st.stdout.strip().split("\n")[:8]:
        print("  " + l[:80])
    sys.exit(2)

head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                      encoding="utf-8", errors="replace", cwd=REPO).stdout.strip()
print("clean tree at %s" % head)

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
    summary = next((l.strip() for l in out.split("\n") if l.startswith("passed ")), "")
    results.append(fails)
    print("run %d: exit=%d  %s  (%.0f s)" % (run_no, r.returncode, summary or "(none)", time.time() - t0))
    if fails:
        print("   failing: %s" % ", ".join(sorted(fails)))

print()
all_fails = set().union(*results)
stable = set.intersection(*results)
flaky = all_fails - stable

if flaky:
    print("checks whose verdict changed between identical runs: %d" % len(flaky))
    for n in sorted(flaky):
        print("  %-30s %s" % (n, " ".join("FAIL" if n in s else "pass" for s in results)))
    print()
    print("DETERMINISM-FAIL (%d)" % len(flaky))
    sys.exit(1)

print("DETERMINISM-PASS (three consecutive runs on a clean tree agree on every verdict)")
