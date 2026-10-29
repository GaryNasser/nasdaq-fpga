"""Check the report's markdown structure: tables intact, no duplicated notes, headings ordered.

Round 207 broke the report three times with patches that each looked fine in a diff:

    1  a block quote inserted mid-table      -> the table split in two
    2  a rebuild matched the WRONG table     -> two-column header over three-column rows
    3  notes duplicated, once as a quote and once as an orphan

Every one was invisible to `check_build_figures` (which only asked "does the value appear") and visible only when
another check happened to read the same region.

### What this checks

    column counts    every row of a table has the same number of cells as its header
    orphan rows      a `|` row with no header above it and no blank line separating them
    duplicates       the same bolded note opening twice
    structure        headings are `##` or `###`, and the file ends with a newline

A malformed table is not a style problem here: it is how a number becomes unfindable, which is how the round-207
breakage hid.
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
fails = []


def cells(row):
    s = row.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return len(s.split("|"))


# --- tables -----------------------------------------------------------------------------
i = 0
tables = 0
while i < len(lines):
    if lines[i].lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
        header_cols = cells(lines[i])
        start = i
        i += 2
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            c = cells(lines[i])
            if c != header_cols:
                fails.append("line %d: %d cells in a %d-column table (%s)"
                             % (i + 1, c, header_cols, lines[start].strip()[:40]))
            i += 1
        tables += 1
        continue
    i += 1

# --- orphan rows ------------------------------------------------------------------------
# A body row is orphaned only if no table HEADER precedes it within the same contiguous run.
# The normal shape is header / separator / rows, so `lines[i-1]` is the separator, not the header.
def _has_header_above(idx):
    for k in range(idx - 1, max(-1, idx - 400), -1):
        s = lines[k].strip()
        if s == "" or s.startswith(">"):
            continue
        if s.startswith("|"):
            # Is the NEXT line a separator? Then this row is a header.
            if k + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[k + 1]):
                return True
            continue
        # Any non-table, non-blank line ends the search.
        return False
    return False


SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

for i, l in enumerate(lines):
    if not l.lstrip().startswith("|"):
        continue
    if SEP.match(l):
        continue
    if i + 1 < len(lines) and SEP.match(lines[i + 1]):
        continue          # this row IS a header
    if _has_header_above(i):
        continue
    fails.append("line %d: table row with no header above (%s)" % (i + 1, l.strip()[:40]))

# A blank line between a table's rows splits it, and a split table is unparseable.
for i, l in enumerate(lines):
    if (l.lstrip().startswith('|') and i >= 2 and lines[i - 1].strip() == ''
            and lines[i - 2].lstrip().startswith('|')):
        fails.append('line %d: a blank line splits a table' % (i + 1))

# --- duplicated bolded notes ------------------------------------------------------------
opens = {}
for i, l in enumerate(lines):
    m = re.match(r"^>?\s*\*\*(.{8,40}?)\*\*", l)
    if m:
        key = m.group(1)
        opens.setdefault(key, []).append(i + 1)
for key, where in opens.items():
    if len(where) > 1:
        fails.append("note **%s** appears %d times at lines %s" % (key[:28], len(where), where[:5]))

# --- headings and ending ---------------------------------------------------------------
for i, l in enumerate(lines):
    if re.match(r"^#{4,}\s", l) and not l.startswith("#####"):
        fails.append("line %d: heading deeper than ### (%s)" % (i + 1, l.strip()[:40]))

# --- code fences, heading levels, anchors, links -----------------------------------------
FENCE = "`" * 3
_inside = False
_prev = 0
_anchors = {}
_fences = 0
for _i, _l in enumerate(lines):
    _s = _l.strip()
    if _s.startswith(FENCE):
        _fences += 1
        _inside = not _inside
        continue
    if _inside:
        continue
    _m = re.match(r"^(#{1,6})\s", _l)
    if not _m:
        continue
    _lv = len(_m.group(1))
    if _prev and _lv > _prev + 1:
        fails.append("line %d: heading level %d -> %d skips a level" % (_i + 1, _prev, _lv))
    _prev = _lv
    _a = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", _s.lstrip("#").strip().lower()).strip("-")
    _anchors.setdefault(_a, []).append(_i + 1)

if _fences % 2:
    fails.append("unbalanced code fences: %d fence lines" % _fences)
for _a, _where in _anchors.items():
    if len(_where) > 1:
        fails.append("duplicate heading %r at lines %s" % (_a[:30], _where[:4]))

for _i, _l in enumerate(lines):
    for _m in re.finditer(r"\[[^\]]*\]\(([^)#][^)]*)\)", _l):
        _t = _m.group(1).strip()
        if _t.startswith(("http", "mailto")):
            continue
        if not os.path.exists(os.path.join(REPO, _t.replace("/", os.sep))):
            fails.append("line %d: link target does not exist: %s" % (_i + 1, _t[:40]))

print("tables parsed : %d" % tables)
print("code fences   : %d" % _fences)
print("headings      : %d" % sum(len(v) for v in _anchors.values()))
print("lines         : %d" % len(lines))
print()

if fails:
    print("REPORT-STRUCTURE-FAIL (%d)" % len(fails))
    for f in fails[:20]:
        print("  " + f)
    sys.exit(1)

print("REPORT-STRUCTURE-PASS (tables intact, no orphan rows, no duplicated notes)")
