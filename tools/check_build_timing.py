"""build_overlay.tcl must print both WNS sources and gate on the live one.

`build_overlay.tcl` computes WNS twice from two different sources, and only one of them gates the build.

    L142  set wns [get_property SLACK [get_timing_paths -delay_type max]]     live query
    L152  report_timing_summary -file .../timing_summary.rpt
    L156  regexp ... -> s_wns s_tns s_whs                                     parsed from that file
    L158  puts "TIMING-METRICS: WNS=$s_wns ..."                               reports the PARSED value
    L164  if { $wns < 0 } { error "TIMING-FAIL: ..." }                        gates on the LIVE value

**Two sources, one name.** If they disagree, the script reports one WNS and refuses the bitstream on another - and
the report downstream quotes whichever a consumer happened to read.

### What can be checked statically

That the live query and the report-backed value are both computed, both printed, and that the gate uses the live
one. Whether they AGREE is a property of a real run and cannot be established without building.

So this audit records the structure and requires that the printed `TIMING-METRICS` line exists - the line the suite
extracts from the build log. A missing or unparsed TIMING-METRICS would leave downstream checks with nothing.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TCL = os.path.join(REPO, "vivado", "build_overlay.tcl")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(TCL, encoding="utf-8", errors="replace").read()
lines = src.split("\n")

print("build_overlay.tcl: %d lines" % len(lines))
print()


def find(pat):
    return [(i + 1, l.strip()) for i, l in enumerate(lines) if re.search(pat, l)]


live = find(r"set\s+wns\s+\[get_property\s+SLACK")
print("live WNS query      : %s" % ([n for n, _ in live] or "none"))
parsed = find(r"->\s*s_wns")
print("parsed WNS capture  : %s" % ([n for n, _ in parsed] or "none"))
metrics = find(r"TIMING-METRICS:")
print("TIMING-METRICS puts : %s" % ([n for n, _ in metrics] or "none"))
gate = find(r"if\s*\{\s*\$wns\s*<\s*0\s*\}")
print("timing gate         : %s" % ([n for n, _ in gate] or "none"))
print()

issues = []

if not live:
    issues.append("no live WNS query")
if not parsed:
    issues.append("the timing summary is not parsed into s_wns")
sources = find(r"TIMING-SOURCES:")
print("TIMING-SOURCES puts : %s" % ([n for n, _ in sources] or "none"))
if not sources:
    issues.append("the two WNS sources are never printed together (round 244)")

if len(metrics) < 2:
    issues.append("TIMING-METRICS is not printed on both the parsed and the fallback path")
if not gate:
    issues.append("the build is not gated on a negative WNS")

# The gate must use the live value, and the metrics line the parsed one - that is what the script chose.
if live and gate:
    gate_line = gate[0][1]
    if "$wns" not in gate_line:
        issues.append("the gate does not use the live WNS value")

# Both sources exist -> state it explicitly, because nothing checks they agree.
if live and parsed:
    print("  NOTE: two WNS sources exist.")
    print("        TIMING-METRICS reports the PARSED value (%s)." % parsed[0][0])
    print("        the build gate uses the LIVE value (%s)." % live[0][0])
    print("        nothing checks they agree - only a build can, and no check reads both from one log.")
    print()

for i in issues:
    print("  ISSUE: " + i)

print()
if issues:
    print("BUILD-TIMING-FAIL (%d)" % len(issues))
    sys.exit(1)
print("BUILD-TIMING-PASS (both WNS sources computed, both paths print TIMING-METRICS, gate on the live value)")
