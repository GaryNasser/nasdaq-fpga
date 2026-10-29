"""Cross-check TABLE figures by column header - the case where the label is structural, not textual.

43 of the 121 figures live in table rows, where a nearby Chinese word is the wrong thing to look for: the label is
the COLUMN HEADER.

    | 项目 | 已上板 bitstream | 第 30 轮重建 | 当前源码 |
    | WNS | +0.126 ns | +0.157 ns | **+0.008 ns** |     <- three WNS values under three columns

The `.rpt` and the report's own tables make this the highest-value case: a table is where a stale figure is most
likely to hide, because the row label is far from the value.

### What this does

For every table, for every column with a unit in the header or a unit-bearing value, collect (table-header-prefix,
column-header, row-label) -> values. A conflict is the same (column, row-label) carrying two values in different
tables that describe the same thing.
"""
import io
import os
import re
import sys
from collections import defaultdict

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NUM = r"(\d[\d,]*\.?\d*)"
UNIT = r"(msg/s|ns/msg|ns|cycles|Gbps|Mbps|pkt/s)"

lines = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read().split("\n")


def cells(row):
    s = row.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

tables = []
i = 0
while i < len(lines):
    if lines[i].lstrip().startswith("|") and i + 1 < len(lines) and SEP.match(lines[i + 1]):
        hdr = cells(lines[i])
        rows = []
        j = i + 2
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            rows.append(cells(lines[j]))
            j += 1
        tables.append((i + 1, hdr, rows))
        i = j
        continue
    i += 1

print("tables parsed: %d" % len(tables))

# (unit, column index) -> list of (table line, row label, value)
seen = defaultdict(list)
units_found = 0
for start, hdr, rows in tables:
    ncols = len(hdr)
    for r in rows:
        if len(r) != ncols:
            continue
        label = r[0]
        for c in range(1, ncols):
            m = re.search(NUM + r"\s*" + UNIT, r[c])
            if not m:
                continue
            units_found += 1
            # Normalise the column to its ORDINAL: two copies of the same table may word the header differently.
            seen[(m.group(2), c, label)].append((start, m.group(1)))

print("unit-bearing table cells: %d" % units_found)
print("distinct (unit, column, row) keys: %d" % len(seen))

conflicts = [(k, v) for k, v in seen.items() if len({x[1] for x in v}) > 1]
print("keys carrying different values: %d" % len(conflicts))
print()
for (unit, col, label), occ in conflicts[:10]:
    print("  %s / %s / %s" % (unit, col[:22], label[:18]))
    for ln, v in occ[:4]:
        print("     L%-5d %s" % (ln, v))

print()
if conflicts:
    print("TABLE-AUDIT-FAIL (%d)" % len(conflicts))
    print("  The same table figure carries different values in two copies of the table.")
    sys.exit(1)

print("TABLE-AUDIT-PASS (%d table cells compared, no conflict)" % units_found)
