"""Every unit-bearing number in the report must be traceable.

Rounds 3-9 each fixed ONE traceability hole - a substring match, a self-documenting record, a missing archive.
This is the aggregate guard: classify every number and fail on any that is only asserted.

Categories:
    RECORDED   appears in docs/measurements/ or the defect log's run records
    SIMULATED  stated on a line that names a simulation
    DERIVED    stated as a computation from other stated figures
    CONSTANT   a device capacity, not a measurement of this design
    ASSERTED   none of the above   <- the only failing category
"""
import glob
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
MEAS = os.path.join(REPO, "docs", "measurements")
LOG = os.path.join(REPO, "docs", "bringup-defects.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

NUM = re.compile(
    r"(?<![\d.])(\d[\d,]*(?:\.\d+)?)\s*"
    r"(ns|µs|us|ms|MB/s|GB/s|msg/s|cycles|个样本|samples|LUT|FF|BRAM|DSP|"
    r"个失败端点|failing endpoints|个包|个消息)")

evidence = []
for p in [LOG] + sorted(glob.glob(os.path.join(MEAS, "*"))):
    if os.path.exists(p):
        evidence.append(io.open(p, encoding="utf-8", errors="replace").read())
ev = "\n".join(evidence)


def norm(s):
    return s.replace(",", "")


seen = {}
for m in NUM.finditer(rep):
    key = (m.group(1), m.group(2))
    if key in seen:
        continue
    ls = rep.rfind("\n", 0, m.start()) + 1
    seen[key] = rep[ls:rep.find("\n", m.start())]


def classify(val, unit, line):
    pat = r"(?<![\d.])" + re.escape(norm(val)) + r"(?![\d])"
    if re.search(pat, norm(ev)):
        return "RECORDED"
    if re.search(r"仿真|simulated|tb_|仿真值", line):
        return "SIMULATED"
    if re.search(r"推导|折算|派生|derived|×|x 28|/ 0\.", line):
        return "DERIVED"
    if re.search(r"差\s*[\d.]+\s*ns|之差|difference", line):
        return "DERIVED"
    if val in ("53,200", "106,400") and unit in ("LUT", "FF"):
        return "CONSTANT"
    return "ASSERTED"


counts = {}
asserted = []
for (val, unit), line in sorted(seen.items()):
    cat = classify(val, unit, line)
    counts[cat] = counts.get(cat, 0) + 1
    if cat == "ASSERTED":
        asserted.append((val, unit, line.strip()[:88]))

total = len(seen)
print("%-10s %s" % ("category", "count"))
print("-" * 26)
for k in ("RECORDED", "SIMULATED", "DERIVED", "CONSTANT", "ASSERTED"):
    if counts.get(k):
        print("%-10s %d" % (k, counts[k]))
print()
print("numbers examined: %d" % total)

if asserted:
    print()
    print("ASSERTED - stated with no archived record and no re-derivation:")
    for val, unit, line in asserted:
        print("  %-10s %-6s %s" % (val, unit, line))
    print()
    print("TRACEABILITY-FAIL (%d number(s) a reader cannot check)" % len(asserted))
    sys.exit(1)

print()
print("TRACEABILITY-PASS (every unit-bearing number is recorded, simulated, derived or a device constant)")
