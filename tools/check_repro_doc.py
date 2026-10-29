"""Compare the checks the report documents with the checks that actually run.

The report's reproduction section says:

    十二项独立检查
    passed 12, failed 0, skipped 0 of 12
    and lists artfacts/regmap/windows/golden/... twelve rows

`run_checks.py` now runs 27. Fifteen checks were added over rounds 80-15 and the
documentation of them was never updated - so a reader following the reproduction
instructions would see a count that does not match, and would not know which
checks exist.

This prints both lists and the difference.
"""
import io
import os
import re
import subprocess
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = r"D:\agent\nasdaq-fpga"
DOC = os.path.join(REPO, "docs", "final-report.md")

text = io.open(DOC, encoding="utf-8", errors="replace").read()

i = text.find("### 9.0")
j = text.find("### 9.0b")
# Round 13: an `assert` here raised AssertionError and killed the check, so a report missing its
# reproduction section reported as a CRASH rather than a failure. A check must always return a verdict.
if i == -1:
    print()
    print("REPRO-DOC-FAIL: section 9.0 is absent - the report has no reproduction section")
    sys.exit(1)
seg = text[i:j if j != -1 else i + 4000]

# Names in the "| `name` | ... |" table rows.
documented = re.findall(r"^\| `(\w+)`", seg, re.M)

# Names in run_checks.py's SUITES table.
rc = io.open(os.path.join(REPO, "tools", "run_checks.py"),
             encoding="utf-8").read()
# Only the CHECKS table. Taking everything up to the next "]" was wrong: the
# table's own entries contain "]" inside their descriptions, so the slice ended
# after the first row and the parse picked up run_sims' suite names instead.
lines = rc.split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("CHECKS"))
end = next(i for i in range(start + 1, len(lines))
           if lines[i].rstrip().endswith("]") and not lines[i].lstrip().startswith("("))
checks_seg = "\n".join(lines[start:end])
implemented = re.findall(r'\(\s*"(\w+)",', checks_seg)

# The stated counts.
m = re.search(r"passed (\d+), failed (\d+), skipped (\d+)(?:, pending \d+)? of (\d+)", seg)
stated = int(m.group(4)) if m else None

print("report section 9.0")
print("  documented checks : %d" % len(documented))
print("  documented count  : %s" % (stated if stated is not None else "?"))
print("  actually running  : %d" % len(implemented))
print()
missing = [c for c in implemented if c not in documented]
stale = [c for c in documented if c not in implemented]
print("in the suite but not documented (%d):" % len(missing))
for c in missing:
    print("  " + c)
if stale:
    print("documented but no longer in the suite (%d):" % len(stale))
    for c in stale:
        print("  " + c)

print()
if missing or stale or (stated is not None and stated != len(implemented)):
    print("REPRO-DOC-STALE")
    sys.exit(1)
print("REPRO-DOC-CURRENT")
