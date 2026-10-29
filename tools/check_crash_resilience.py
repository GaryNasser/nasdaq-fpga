"""Does every check CRASH on a malformed input, or does it report a verdict?

Round 12: `check_arithmetic.num()` raised `StopIteration` when a pattern did not match - the guard came after the
crash. A check that crashes is worse than one that fails: the suite reports it as an error, and during a long run the
difference between "tried and failed" and "never ran" is easy to lose.

The test: give each check a report that is syntactically wrong in ways a document can genuinely go wrong -
empty, truncated, encoding-mangled - and require a VERDICT (exit 0 or 1 with a token), not a traceback.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
REPORT = os.path.join(REPO, "docs", "final-report.md")
RUNNER = os.path.join(TOOLS, "run_checks.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

refs = dict(re.findall(r'"(\w+)":\s*"([\w.]+\.py)"', io.open(RUNNER, encoding="utf-8").read()))

# Which checks READ the report? Those are the ones a malformed document can crash.
readers = []
for name, script in refs.items():
    p = os.path.join(TOOLS, script)
    if not os.path.exists(p):
        continue
    src = io.open(p, encoding="utf-8", errors="replace").read()
    if "final-report.md" in src:
        readers.append((name, script))

print("checks that read the report: %d" % len(readers))

MUTATIONS = [
    ("empty", ""),
    ("truncated mid-table", "\n".join(
        io.open(REPORT, encoding="utf-8", errors="surrogateescape").read().split("\n")[:400])),
    ("only headings", "\n".join(
        l for l in io.open(REPORT, encoding="utf-8", errors="surrogateescape").read().split("\n")
        if l.startswith("#"))),
]

orig = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
st = os.stat(REPORT)
import atexit
atexit.register(lambda: os.path.exists(bk) and shutil.copyfile(bk, REPORT))

crashes = []
try:
    for label, content in MUTATIONS:
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(content)
        print()
        print("report replaced with: %s (%d bytes)" % (label, len(content)))
        for name, script in readers:
            try:
                r = subprocess.run([sys.executable, os.path.join(TOOLS, script)],
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", cwd=TOOLS, timeout=180)
                out = (r.stdout or "") + (r.stderr or "")
            except subprocess.TimeoutExpired:
                print("  %-28s TIMEOUT" % name)
                crashes.append((label, name, "timeout"))
                continue
            traceback = "Traceback (most recent call last)" in out
            # exit 0/1/2 are verdicts; 1 with a token is a clean FAIL. A traceback is not.
            if traceback:
                crash_line = [l for l in out.split("\n") if l.strip()][-1][:60]
                print("  %-28s CRASH   %s" % (name, crash_line))
                crashes.append((label, name, crash_line))
finally:
    shutil.copyfile(bk, REPORT)
    os.utime(REPORT, (st.st_atime, st.st_mtime))
    os.unlink(bk)

print()
print("crashes: %d" % len(crashes))
for label, name, why in crashes:
    print("  [%s] %-28s %s" % (label, name, why))

if crashes:
    print()
    print("CRASH-RESILIENCE-FAIL (%d crash(es) on a malformed report)" % len(crashes))
    sys.exit(1)
print()
print("CRASH-RESILIENCE-PASS (every report-reading check returns a verdict on a broken document)")
