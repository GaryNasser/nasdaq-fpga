"""Does every check that verifies a NUMBER accept a longer number containing its digits?

Round 3 found `615` matching inside `2203615`. Round 4 found four more of the same shape in
`check_figure_derive`. **The general property is testable**: for each figure a check requires, substitute a value
that CONTAINS it and confirm the check fails.

A check that says PASS when the document holds `66.77` instead of `66.7` is reporting on a document it did not read.
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# (check script, figures it requires, report)
CASES = [
    ("check_figure_derive.py", ["94.5", "66.7", "28.252", "299.01", "3.10"]),
    # audit_numbers checks exact counts and md5s; a count is the case where a longer number
    # containing the digits would satisfy a plain in.
    ("audit_numbers.py", ["4,524", "5,437"]),   # round 43: the round-41 rebuild moved these
]


def run(script):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, script)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
st = os.stat(REPORT)
import atexit
atexit.register(lambda: os.path.exists(bk) and shutil.copyfile(bk, REPORT))

holes = []
tested = 0

try:
    for script, figures in CASES:
        rc0, _ = run(script)
        if rc0 != 0:
            print("  %-26s baseline FAILS - cannot test" % script)
            holes.append((script, "baseline"))
            continue
        for fig in figures:
            if fig not in original:
                continue
            tested += 1
            # Append a digit: the report no longer states `fig`, it states a different number.
            mutated = original.replace(fig, fig + "9")
            io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
            rc, out = run(script)
            landed = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read() != original
            caught = rc != 0
            print("  %-26s %-8s +digit  landed=%s %s"
                  % (script, fig, landed, "CAUGHT" if caught else "*** MISSED ***"))
            if landed and not caught:
                holes.append((script, fig))
finally:
    shutil.copyfile(bk, REPORT)
    os.utime(REPORT, (st.st_atime, st.st_mtime))
    os.unlink(bk)

print()
print("figures tested : %d" % tested)
print("substring holes: %d" % len(holes))
for h in holes:
    print("   %s  %s" % h)

if holes:
    print()
    print("NUMERIC-MATCH-FAIL (%d figure(s) matched as a substring of a different number)" % len(holes))
    sys.exit(1)
print()
print("NUMERIC-MATCH-PASS (every required figure is matched as a whole number)")
