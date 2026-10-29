"""Cross-check performance figures ACROSS sections (phrase before the number: the same metric quoted in two places must agree.

Every figure in the report has a source. **That does not make the figures consistent with each other.** The
throughput appears in the summary, in section 5, in the comparison table and in the status file; if two of those
disagree, both can cite a real measurement - of different runs.

### What this checks

    a quantity is a number followed by a unit token (msg/s, ns/msg, Gbps, cycles)
    the same (label, unit) pair appearing in several places must carry the same value
    unless the report marks the difference as intentional (历史 | 早前 | 此前 | 那次构建)
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

lines = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read().split("\n")

# (number, unit) with a nearby label word.
# Percentages and ratios are excluded: their denominator is contextual, and the arithmetic that
# makes them right is checked by check_timing_arith and check_speedup.
UNIT = r"(msg/s|ns/msg|ns|cycles|Gbps|Mbps|pkt/s)"
NUM = r"(\d[\d,]*\.?\d*)"

# Marker words that say a line describes a DIFFERENT run. Round 247: these used to `continue`, which skipped
# the whole line - so a real contradiction carrying the phrase was invisible. **Round 219 wrote that lesson down
# and did not fix it.** The line now still contributes its figures; the marker only excuses it from agreeing.
HISTORICAL = re.compile("\u5386\u53f2|\u65e9\u524d|\u6b64\u524d|\u90a3\u6b21\u6784\u5efa|\u65e7\u6784\u5efa|superseded|\u5f53\u65f6")
CONTRAST = re.compile('\u4ee5\u4e0a\u662f|\u677f\u4e0a\u5b9e\u6d4b|\u4eff\u771f\u503c|\u5bf9\u6bd4')

# The round a line names is part of its identity. "\u7b2c 30 \u8f6e\u91cd\u5efa\uff08+0.157 ns\uff09" and
# "\u7b2c 41 \u8f6e\u91cd\u5efa\uff08+0.094 ns\uff09" both reduce to the label \u8f6e\u91cd\u5efa, so the audit reported a
# contradiction between two figures that are correct statements about two different
# builds - exactly what a reader is told to distinguish. Naming the round in the line is
# the "state which run it came from" the failure message asks for, so it must split the key.
ROUND = re.compile(r"\u7b2c\s*(\d+)\s*\u8f6e")

pairs = defaultdict(list)
for i, l in enumerate(lines):
    # A line that contrasts two runs in words, or marks itself historical, may legitimately carry a value that
    # differs from another line. It is recorded - and COUNTED - but keyed separately so it cannot conflict.
    tagged = HISTORICAL.search(l) or CONTRAST.search(l)
    samp = re.search(r'(\d{3,6})\s*(?:\u4e2a\u6837\u672c|\u6837\u672c)', l)
    rnd = ROUND.search(l)
    for m in re.finditer("([\u4e00-\u9fff]{2,10})[^\\d\\n]{0,8}" + NUM + r"\s*" + UNIT, l):
        label, num, unit = m.group(1), m.group(2), m.group(3)
        # Tagged lines get their own bucket: a figure stated in a contrast sentence is not compared against the
        # bare restatement, but BOTH are still in `pairs` and so still counted.
        key = (label, unit, samp.group(1) if samp else "", "tagged" if tagged else "plain",
               ("round " + rnd.group(1)) if rnd else "")
        pairs[key].append((i + 1, num))

conflicts = []
for (label, unit, _s, _kind, _rnd), occ in pairs.items():
    vals = {re.sub(r",", "", n) for _, n in occ}
    if len(vals) > 1 and len(occ) >= 2:
        conflicts.append((label, unit, occ))

_bare = len(re.findall(NUM.replace("(", "(?:") + r"\s*" + UNIT, io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()))
_labelled = sum(len(v) for v in pairs.values())
print("figures with a unit          : %d" % _bare)
print("  ...compared (label on the same line): %d" % _labelled)
print("  ...skipped  (label on another line): %d" % max(0, _bare - _labelled))
print()
print("label/unit pairs found: %d" % len(pairs))
print("pairs with more than one value: %d" % len(conflicts))
print()
for label, unit, occ in conflicts[:14]:
    print("  %s (%s)" % (label, unit))
    for ln, v in occ[:5]:
        print("     L%-5d %s" % (ln, v))

print()
if conflicts:
    print("CROSSNUM-AUDIT-FAIL (%d)" % len(conflicts))
    print("  The same quantity is quoted with different values in different places.")
    print("  Either mark the differing one as historical, state which run it came from, or fix it.")
    sys.exit(1)

print("CROSSNUM-AUDIT-PASS (every quantity quoted more than once carries one value)")
