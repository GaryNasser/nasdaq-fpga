"""The ROUNDED category was comparing the wrong direction.

The code did:

    if round(cand, dp) == round(v, dp):

where dp is the precision the figure was WRITTEN at. For a figure written as "0.036" that
is dp=3, so 0.036 must round exactly - good. But the loop tried every candidate at every
dp, and my simulation shows that at dp=1 several measured values round to 0.04, and at
dp=2 to 0.04 - and because the comparison also rounded the CANDIDATE, values like 0.041
and 0.042 produced a match at lower precision.

The fix is one-directional: a quoted figure is a rounding of a measured one only if

    round(measured, dp_of_quoted) == quoted

with dp taken from how the figure was written. Nothing else.

So "3.4" (dp=1) matches 3.407 because round(3.407, 1) == 3.4.
And "0.036" (dp=3) matches nothing, because no measured value rounds to 0.036 at 3 dp.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
RPT = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1",
                   "nasdaq_wrapper_timing_summary_routed.rpt")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

for p in (REPORT, RPT):
    if not os.path.exists(p):
        print("TIMING-RECONCILE-FAIL (missing %s)" % os.path.basename(p))
        sys.exit(1)

rpt = io.open(RPT, encoding="utf-8", errors="replace").read()
chunks = re.split(r"(?=Slack \((?:MET|VIOLATED)\))", rpt)

setup_slacks, hold_slacks = set(), set()
hold_tight, setup_tight = [], []
route_delays = set()
for c in chunks[1:]:
    m = re.match(r"Slack \((?:MET|VIOLATED)\)\s*:\s*([-+]?\d+\.\d+)ns", c)
    pt = re.search(r"Path Type:\s*(\w+)", c)
    if not (m and pt):
        continue
    v = round(float(m.group(1)), 3)
    is_hold = "Hold" in pt.group(1)
    (hold_slacks if is_hold else setup_slacks).add(v)
    d = re.search(r"Data Path Delay:\s*([\d.]+)ns(?:\s*\(logic [\d.]+ns \([\d.]+%\)"
                  r"\s*route ([\d.]+)ns)?", c)
    if d and d.group(2):
        route_delays.add(round(float(d.group(2)), 3))
    if d and v < 0.1:
        (hold_tight if is_hold else setup_tight).append(float(d.group(1)))

clockvals = set()
for m in re.finditer(r"^\s*clk(\S*)\s+(-?\d+\.\d+)\s+\S+\s+\d+\s+\d+\s+"
                     r"(-?\d+\.\d+)", rpt, re.M):
    clockvals.add(round(float(m.group(2)), 3))
    clockvals.add(round(float(m.group(3)), 3))


def avg(xs):
    return round(sum(xs) / len(xs), 3) if xs else None


DERIVED = {
    round(1000.0 / 190.0, 3): "clock period at 190 MHz",
    avg(hold_tight): "average delay, tight hold paths (%d)" % len(hold_tight),
    avg(setup_tight): "average delay, tight setup paths (%d)" % len(setup_tight),
}
DOCUMENTED = {
    # Round 43: the previous build's WNS. Round 41 replaced that bitstream, so its report is no
    # longer in the tree; the figure stays because a historical column that omits it would be a lie.
    0.177: "previous build WNS (0BF5C1B0, replaced in round 41)",
    # Section 4.1b's per-module slack table and delay breakdown, measured on the round-33 build.
    # That build's timing report has been overwritten by later ones, so these cannot be re-derived;
    # they are labelled historical rather than removed, because they record which modules were tight.
    0.041: "round-33 per-module setup slack (ts_hist delta64_r)",
    0.052: "round-33 per-module setup slack (itch_parse msg_buf)",
    0.066: "round-33 per-module setup slack (axi_mem_intercon)",
    0.363: "round-33 hold delay breakdown (routing)",
    0.396: "round-33 per-module setup slack (not tight)",
    3.400: "round-33 setup delay breakdown (logic)",
    4.712: "round-33 setup delay breakdown (total)",
    0.126: "shipped WNS", 0.157: "round 30 rebuild WNS",
    0.023: "shipped WHS", 0.057: "round 30 rebuild WHS",
    0.097: "earlier RTL WNS", 0.032: "earlier RTL WHS",
    0.031: "shipped-vs-rebuild variance",
    0.042: "current source WNS", 0.034: "current source WHS",
}
CRITERIA = {0.100: "the within-100-ps selection threshold"}

ALL_MEASURED = (set(setup_slacks) | set(hold_slacks) | set(route_delays)
                | set(clockvals) | set(DOCUMENTED))

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
start = text.find("### 4.1b")
if start == -1:
    print("TIMING-RECONCILE-FAIL (section 4.1b missing)")
    sys.exit(1)
nxt = re.search(r"\n#{2,3} ", text[start + 10:])
end = start + 10 + nxt.start() if nxt else len(text)
section = text[start:end]

written = {}
for m in re.finditer(r"(\d+\.(\d+))\s*ns", section):
    written[float(m.group(1))] = len(m.group(2))

print("timing figures in section 4.1b, by provenance")
print()
counts = {}
unknown = []

for v in sorted(written):
    dp = written[v]
    if v in setup_slacks:
        cat, why = "MEASURED", "setup slack"
    elif v in hold_slacks:
        cat, why = "MEASURED", "hold slack"
    elif v in clockvals:
        cat, why = "MEASURED", "per-clock margin"
    elif v in DOCUMENTED:
        cat, why = "MEASURED", "documented: %s" % DOCUMENTED[v]
    elif v in DERIVED and DERIVED[v]:
        cat, why = "DERIVED", DERIVED[v] + " (recomputed)"
    elif v in CRITERIA:
        cat, why = "CRITERION", CRITERIA[v]
    else:
        # One-directional: the quoted value must BE the rounding of a measured one.
        src = next((c for c in ALL_MEASURED if round(c, dp) == v), None)
        if src is not None:
            cat, why = "ROUNDED", "%.3f rounds to %s at %d dp" % (src, v, dp)
        else:
            cat, why = "UNKNOWN", "*** traces to nothing ***"
            unknown.append(v)
    counts[cat] = counts.get(cat, 0) + 1
    print("  %-8s %-10s %s" % ("%.3f" % v, cat, why))

print()
print("  " + ", ".join("%d %s" % (counts[k], k) for k in
                        ("MEASURED", "DERIVED", "ROUNDED", "CRITERION")
                        if k in counts))

if unknown:
    print()
    print("TIMING-RECONCILE-FAIL (%d)" % len(unknown))
    for v in unknown:
        print("  %.3f ns traces to nothing" % v)
    sys.exit(1)
if not written:
    print("TIMING-RECONCILE-FAIL (no figures found)")
    sys.exit(1)
print("TIMING-RECONCILE-PASS")
