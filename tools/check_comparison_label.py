"""A comparison table's column must say which side is measured and which is simulated.

Round 12: section 7's table read

    | 口径 | A9 基线（实测） | PL | 加速比 |

The A9 column was labelled 实测 and the PL column was not - so a reader takes BOTH as measured, and reads "3.10x" as
an end-to-end speedup. **The PL figure is a simulation cycle count.** The ratio is simulated-design versus
measured-software.

`check_measured_trace` guards individual NUMBERS. This guards the LABEL a whole column carries, because one mislabel
covers every row beneath it.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

lines = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read().split("\n")

# Column labels that assert a provenance.
MEASURED = re.compile(r"实测|measured")
SIMULATED = re.compile(r"仿真|simulated")

problems = []
checked = 0

for n, line in enumerate(lines, 1):
    s = line.strip()
    if not s.startswith("|"):
        continue
    cells = [c.strip() for c in s.strip("|").split("|")]
    if len(cells) < 3:
        continue
    # Is this a header row?  The next line must be a separator.
    if n >= len(lines) or not re.match(r"^\|[\s:|-]+\|?$", lines[n].strip()):
        continue
    checked += 1
    header = " | ".join(cells)

    # A table that compares a simulated design against a measured baseline must say so.
    has_measured = any(MEASURED.search(c) for c in cells)
    has_simulated = any(SIMULATED.search(c) for c in cells)
    mentions_ratio = any(re.search(r"加速比|speedup|倍数|ratio", c, re.I) for c in cells)

    if mentions_ratio and has_measured and not has_simulated:
        # Which columns hold the design's own figures?
        design_cols = [c for c in cells if re.search(r"^PL$|^FPGA$|^硬件$", c)]
        if design_cols:
            problems.append((n, header))
            print("  L%-5d ratio table, baseline marked measured, design column UNMARKED" % n)
            print("         %s" % header[:100])

print()
print("comparison tables with a provenance label: %d" % checked)

if problems:
    print()
    print("COMPARISON-LABEL-FAIL (%d table(s) present a simulated figure beside a measured one"
          " without saying which is which)" % len(problems))
    sys.exit(1)

print()
print("COMPARISON-LABEL-PASS (every ratio table names the provenance of both sides)")
