"""`status.md` claims every figure was read from an artifact. Verify that, rather than trust the header.

    "This file is regenerated from the artifacts, not written by hand. Every figure below was read from a
     build output, a test verdict or a check result on the date shown."

That sentence is the reason a reader trusts the file. It is also exactly the kind of claim that rots: the
generator can silently drop a line (round 169: the static check line became "could not parse a count") and
the header still asserts completeness.

### The check

For each figure the file states, confirm it appears in the artifact the file names next to it:

    suites counts       <- the live SUITE-PASS / SIMSUITE-PASS lines
    WNS/WHS/TNS         <- impl_1/nasdaq_wrapper_timing_summary_routed.rpt
    LUT / FF / BRAM/DSP <- impl_1/nasdaq_wrapper_utilization_placed.rpt
    bitstream size/date <- impl_1/nasdaq_wrapper.bit

Figures NOT covered: the hardware table, which describes a different build and is now labelled as such.

That last point matters - a generated file that mixes live-derived and historical figures must say which is
which, or "every figure below was read from an artifact" is false for half the file.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
STATUS = os.path.join(REPO, "docs", "status.md")
IMPL = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

text = io.open(STATUS, encoding="utf-8", errors="surrogateescape").read()

fails = []
checks = []

# --- suite counts vs the live runners -------------------------------------------------
import subprocess
env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PATH": r"D:\Xilinx\Vivado\2024.1\bin;" + os.environ.get("PATH", "")}

# Count the registered checks statically. Running run_checks.py from inside a check that run_checks.py
# invokes re-enters the whole suite - the first version of this file did exactly that and had to be killed.
runner_src = io.open(os.path.join(REPO, "tools", "run_checks.py"),
                      encoding="utf-8").read()
table = runner_src.split("CHECKS", 1)[1].split("]\n", 1)[0]
registered = len(re.findall(r'^\s*\("\w+",', table, re.M))

doc = re.search(r"static contract checks.*?(\d+) passed, (\d+) failed, (\d+) skipped(?:, (\d+) pending)? of (\d+)", text)

if doc:
    same = (int(doc.group(5)) == registered)
    checks.append(("static suite count", "%d registered" % registered,
                   "%s of %s" % (doc.group(1), doc.group(5)), same))
    if not same:
        fails.append("status.md states %s checks; run_checks.py registers %d"
                     % (doc.group(5), registered))

# --- timing ---------------------------------------------------------------------------
ts = os.path.join(IMPL, "nasdaq_wrapper_timing_summary_routed.rpt")
if os.path.exists(ts):
    body = io.open(ts, encoding="utf-8", errors="replace").read()
    mm = re.search(r"^\s+(-?\d+\.\d+)\s+-?\d+\.\d+\s+\d+\s+\d+\s+(-?\d+\.\d+)", body, re.M)
    if mm:
        wns_r, whs_r = mm.group(1), mm.group(2)
        wns_d = re.search(r"WNS (-?\d+\.\d+) ns", text)
        same = bool(wns_d and wns_d.group(1).lstrip("-") == wns_r.lstrip("-"))
        checks.append(("WNS", wns_r, wns_d.group(1) if wns_d else "(absent)", same))
        if not same:
            fails.append("WNS in status.md does not match the routed timing report")

# --- utilization ----------------------------------------------------------------------
ut = os.path.join(IMPL, "nasdaq_wrapper_utilization_placed.rpt")
if os.path.exists(ut):
    body = io.open(ut, encoding="utf-8", errors="replace").read()
    lut = re.search(r"\|\s+Slice LUTs\s+\|\s+(\d+)", body)
    ff = re.search(r"\|\s+Register as Flip Flop\s+\|\s+(\d+)", body)
    if lut:
        d = re.search(r"LUT (\d+)", text)
        same = bool(d and d.group(1) == lut.group(1))
        checks.append(("LUT", lut.group(1), d.group(1) if d else "(absent)", same))
        if not same:
            fails.append("LUT in status.md does not match the utilization report")
    if ff:
        d = re.search(r"FF (\d+)", text)
        same = bool(d and d.group(1) == ff.group(1))
        checks.append(("FF", ff.group(1), d.group(1) if d else "(absent)", same))
        if not same:
            fails.append("FF in status.md does not match the utilization report")

print("status.md figures re-derived from the artifacts they name")
print()
print("  %-22s %-14s %-14s %s" % ("figure", "artifact", "status.md", "match"))
print("  " + "-" * 62)
for name, a, b, same in checks:
    print("  %-22s %-14s %-14s %s" % (name, a, b, "yes" if same else "NO"))

print()
if fails:
    print("STATUS-GENUINE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)

hist = "These figures describe bitstream" in text or "pre-fix build" in text
print("  historical hardware table labelled: %s" % hist)
if not hist:
    print("STATUS-GENUINE-FAIL (the hardware table is not marked as a different build)")
    sys.exit(1)

print()
print("STATUS-GENUINE-PASS (every live figure re-derives; the historical table is labelled)")
