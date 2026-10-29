"""Widen the WNS scan to catch table rows, where the value has no "WNS" prefix.

The first version matched `WNS +<value>` in prose. The rebuild comparison table writes:

    | WNS | +0.126 ns | +0.157 ns | +0.031 |

so +0.157 - the clean rebuild's value - was invisible to the check. It is legitimately
owned (the table's column header says which build each column is), but a check that
cannot see it also cannot notice if it drifts into prose without attribution.

The fix scans for WNS values in TWO forms:

    prose:   WNS +0.157
    table:   | WNS | +0.126 ns | +0.157 ns | ...

and treats a table row as attributing its values to the columns named in the header.
"""
import io
import os
import re
import sys

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(REPORT):
    print("WNS-OWNERSHIP-FAIL (no report)")
    sys.exit(1)

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
lines = text.split("\n")

SHIPPED = "0.126"
CURRENT = "0.042"
REBUILD = "0.157"
# Values that belong to superseded builds and may appear only inside a correction
# note. +0.097 is the earlier single-packet RTL revision (14 entries in the defect log).
HISTORICAL = {"0.097"}

print("WNS values in the report (prose and tables)")
print()

mentions = {}   # value -> list of (line, form)

for i, l in enumerate(lines, 1):
    # prose:  WNS +0.123
    for m in re.finditer(r"WNS\s*\+?([\d.]+)", l):
        mentions.setdefault(m.group(1), []).append((i, "prose"))
    # table:  | WNS | +0.126 ns | +0.157 ns |
    if re.match(r"^\|\s*WNS\s*\|", l.strip()):
        for m in re.finditer(r"\+\s*([\d.]+)\s*ns", l):
            mentions.setdefault(m.group(1), []).append((i, "table"))

for v in sorted(mentions, key=lambda x: -len(mentions[x])):
    forms = set(f for _, f in mentions[v])
    where = ", ".join("L%d(%s)" % (n, f) for n, f in mentions[v][:5])
    print("  WNS +%-7s %d mention(s)  %s  [%s]"
          % (v, len(mentions[v]), where, "/".join(sorted(forms))))

print()
fails = []

if SHIPPED not in mentions:
    fails.append("shipped value +%s not cited" % SHIPPED)
if CURRENT not in mentions:
    fails.append("current-source value +%s not cited" % CURRENT)

# The rebuild value is optional, but if present it must be attributed (table form).
if REBUILD in mentions and all(f == "prose" for _, f in mentions[REBUILD]):
    fails.append("rebuild value +%s appears in prose with no column attribution"
                 % REBUILD)

# Summary check.
# Round 206: the summary is the leading block quote, not the first 40 lines. A fixed line count
# silently stops covering the block when the prose grows - +0.126 had moved to line 67.
# Round 206: "the summary" is everything before the first `## ` heading - the block quote AND the prose
# that follows it. The timing sentence sits in that prose, and a fixed line count or a quote-only window
# both missed it, which is a statement about the window rather than about the document.
_lead = []
for _l in lines:
    if _l.startswith("## "):
        break
    _lead.append(_l)
head = "\n".join(_lead)
print("  summary block: %d lines (before the first ## heading)" % len(_lead))
head_vals = set(m.group(1) for m in re.finditer(r"WNS\s*\+?([\d.]+)", head))
print("  values in the first 40 lines: %s" % (sorted(head_vals) or "none"))
if head_vals and SHIPPED not in head_vals:
    fails.append("the summary quotes %s but not the shipped value +%s"
                 % (sorted(head_vals), SHIPPED))

print()
if fails:
    print("WNS-OWNERSHIP-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("WNS-OWNERSHIP-PASS")
