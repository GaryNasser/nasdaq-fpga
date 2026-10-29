"""The last two mutations did not apply to the text the patterns read.

    94.5 MB/s -> 120.0 MB/s     the pattern is  应为 \\*\\*(\\d+\\.\\d+) MB/s\\*\\*
                                so the text to change is "应为 **94.5 MB/s**" - the plain
                                "94.5 MB/s" may occur elsewhere and be edited instead.

    33.3% -> 10.0%              the pattern is  差额[^\\n]*?\\*\\*(\\d+\\.\\d+)%\\*\\*
                                the text to change is "**33.3%**" after 差额, not any "33.3".

Mutating "94.5" in a different sentence leaves the pattern's target untouched, the quoted value
unchanged, and the check correctly passes. Eighth mutation-position mistake in this series.

Target the exact spans the patterns match.
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
CHK = os.path.join(REPO, "tools", "check_arithmetic.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

CASES = []
m = re.search(r"应为 \*\*(\d+\.\d+) MB/s\*\*", original)
if m:
    CASES.append(("simulated MB/s %.1f -> 120.0" % float(m.group(1)),
                  original[:m.start(1)] + "120.0" + original[m.end(1):]))
m = re.search(r"差额[^\n]*?\*\*(\d+\.\d+)%\*\*", original)
if m:
    CASES.append(("gap %.1f%% -> 10.0%%" % float(m.group(1)),
                  original[:m.start(1)] + "10.0" + original[m.end(1):]))

results = []
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    for label, mutated in CASES:
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
                newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        results.append((label, caught))
        line = next((l.strip() for l in out.splitlines() if "MISMATCH" in l), "")
        print("%-34s exit=%d %s  %s" % (label, rc, "CAUGHT" if caught else "MISSED",
                                        line[:46]))
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("ARITHMETIC-PROOF-FAIL")
sys.exit(1)
