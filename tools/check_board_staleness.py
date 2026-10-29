"""Do the checks treat archived board numbers as still true while the board is gone?

Rounds 15-18 took five board measurements. They are archived, and the report cites them. **None of them can be
re-taken while the board is offline** - which is correct and expected.

What would be wrong is a claim that reads as a CURRENT observation when it is an archived one.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
lines = text.split("\n")

ARCHIVES = ["state-carryover", "order-map-crossing", "bbo-across-replays", "stability-20-resets"]

# Where the report points at each archive.
cit = {a: [n for n, l in enumerate(lines, 1) if a in l] for a in ARCHIVES}
print("archive citations:")
for a in ARCHIVES:
    print("  %-22s %s" % (a, cit[a] or "(none)"))

# A caveat must (a) mention board availability, (b) name one of these archives, and (c) sit within
# 10 lines of a citation. Naming the archive is what stops a row that merely DESCRIBES a tool from
# satisfying it - the round-4 trap.
CAVEAT = re.compile(r"(?:离线|offline|重新上电|power cycle|无法.{0,12}重新|cannot be re-?taken)", re.I)

good = None
for n, line in enumerate(lines, 1):
    if not CAVEAT.search(line):
        continue
    nearby = "\n".join(lines[max(0, n - 10):n + 10])
    names = [a for a in ARCHIVES if a in nearby]
    if not names:
        continue
    if any(abs(n - c) <= 10 for a in names for c in cit.get(a, [])):
        good = (n, line.strip()[:90], names)
        break

print()
if good:
    n, line, names = good
    print("caveat at L%d names %s and sits beside the citation:" % (n, ", ".join(names)))
    print("  %s" % line)
    print()
    print("BOARD-STALENESS-PASS (the archived board figures are marked as not re-takeable)")
    sys.exit(0)

print("BOARD-STALENESS-FAIL: board measurements are cited without a caveat tying them to board availability")
print("  A caveat that merely describes a TOOL does not count - it must name an archive.")
sys.exit(1)
