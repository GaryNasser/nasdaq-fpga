import glob
"""Pick the REPRODUCIBILITY table, not the section 4.1 timing table.

Round 47 rewrote section 4.1 to have two columns headed 已上板 bitstream and 当前源码.
Round 48 rewrote the reproducibility table to have THREE columns: shipped, round-30
rebuild, current source.

Both start with "| 项目 |" and both contain "已上板", so the check's locator picked the
first one it found - section 4.1, which has no LUT/FF rows at all - and then correctly
reported those figures missing from a table that never had them.

The discriminator is the presence of a resource row. The reproducibility table has
"| LUT |"; the timing table does not. Selecting on that is precise and survives future
edits to either table's wording.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
UTIL = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1",
                    "nasdaq_wrapper_utilization_placed.rpt")
LOG = os.path.join(REPO, "build_check", "experiment_mcyc.log")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

for p in (REPORT, UTIL):
    if not os.path.exists(p):
        print("BUILD-FIGURES-FAIL (missing %s)" % os.path.basename(p))
        sys.exit(1)

u = io.open(UTIL, encoding="utf-8", errors="replace").read()


def grab(pat):
    m = re.search(pat, u)
    return int(m.group(1)) if m else None


lut = (grab(r"\|\s+LUT as Logic\s+\|\s+(\d+)") or 0) + \
      (grab(r"\|\s+LUT as Memory\s+\|\s+(\d+)") or 0)
ff = grab(r"\|\s+Register as Flip Flop\s+\|\s+(\d+)")
bram = grab(r"\|\s+Block RAM Tile\s+\|\s+(\d+)")
dsp = grab(r"\|\s+DSPs\s+\|\s+(\d+)")

wns = None
# Round 206: the routed timing report is the authority. The `TIMING-METRICS:` log line only exists in
# some builds, so reading it first means the checker silently uses whichever old log still has one.
_rpt_glob = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1",
                         "*timing_summary_routed.rpt")
_cands = sorted(glob.glob(_rpt_glob))
if _cands:
    _t = io.open(_cands[0], encoding="utf-8", errors="replace").read()
    _m = re.search(r"^\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)\s", _t, re.M)
    if _m and "WNS(ns)" in _t:
        wns = _m.group(1)
if wns is None and os.path.exists(LOG):
    lg = io.open(LOG, encoding="utf-8", errors="replace").read()
    m = re.search(r"TIMING-METRICS: WNS=(-?[\d.]+)", lg)
    if m:
        wns = m.group(1)

lines = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read().split("\n")


def tables():
    """Yield (start, end) spans for every markdown table."""
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            yield i, j
            i = j
        else:
            i += 1


# The reproducibility table is the one that has a LUT row AND claims a current build.
# Round 250: TWO tables match (L193 section 4.1 and L425 the reproducibility table), and taking only the
# first meant the other was never compared. Collect them all.
targets = []
for s, e in tables():
    block = "\n".join(lines[s:e])
    if re.search(r"^\|\s*LUT\s*\|", block, re.M) and "当前源码" in block:
        targets.append((s, e))

target = targets[0] if targets else None
print("  tables claiming a current build: %d  (lines %s)"
      % (len(targets), ", ".join(str(s + 1) for s, _ in targets)))

print("current build (impl_1) vs the reproducibility table")
print()
print("  impl_1 says: LUT %d, FF %s, BRAM %s, DSP %s, WNS %s"
      % (lut, ff, bram, dsp, wns))

if target is None:
    print("  no table with a LUT row and a current-build column")
    print()
    print("BUILD-FIGURES-FAIL (1)")
    print("  the reproducibility table was not found")
    sys.exit(1)

s, e = target
table = "\n".join(lines[s:e])
print("  table found at lines %d..%d" % (s + 1, e))
print()

fails = []

for label, value in (("LUT", format(lut, ",")), ("FF", format(ff, ",")),
                     ("BRAM", str(bram)), ("DSP", str(dsp))):
    # Round 250: "the value appears somewhere in the table" is too weak - removing the CURRENT column leaves
    # the number in the shipped or rebuild column and the check still passes. Require the last column,
    # which is the one the header marks as 当前源码.
    _rows = [ln for ln in table.split(chr(10)) if ln.lstrip().startswith("|") and label in ln]
    _cells = []
    for _ln in _rows:
        _parts = [c.strip() for c in _ln.strip().strip("|").split("|")]
        if _parts:
            _cells.append(_parts[-1].replace("*", "").strip())
    present = any(value.replace(",", "") in c.replace(",", "") for c in _cells)
    print("  %-5s %-6s in the table : %s" % (label, value, present))
    if not present:
        fails.append("%s %s is not in the reproducibility table" % (label, value))

if wns:
    present = ("+%s" % wns) in table
    print("  WNS   %-6s in the table : %s" % (wns, present))
    if not present:
        fails.append("WNS +%s is not in the reproducibility table" % wns)

print()
if fails:
    print("BUILD-FIGURES-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
# Round 250: every table claiming a current build must match, not just the first.
_others = targets[1:]
_bad = []
for _s, _e in _others:
    _b = chr(10).join(lines[_s:_e])
    for _label, _val in (("LUT", lut), ("FF", ff), ("BRAM", bram), ("DSP", dsp)):
        # Values may share a row ("| BRAM / DSP | 14 / 0 |"), so match the NUMBER anywhere in the row
        # whose label contains the key.
        _num = "{:,}".format(_val) if _val else "0"
        _rows = [ln for ln in _b.split(chr(10)) if _label in ln and ln.lstrip().startswith("|")]
        if not any(_num in ln for ln in _rows):
            _bad.append("%s missing %s=%s" % ("L%d" % (_s + 1), _label, _val))
if _bad:
    print()
    print("BUILD-FIGURES-FAIL (%d)" % len(_bad))
    for _x in _bad:
        print("  " + _x)
    sys.exit(1)

print("BUILD-FIGURES-PASS (the reproducibility table matches impl_1)")
