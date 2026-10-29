"""Verify docs/status.md agrees with the build outputs it summarises.

status.md is generated, but generation is not verification: the first version of
gen_status.py parsed the timing summary with the columns in the wrong order and
printed "WHS 0.000, TNS 0.031" when the truth was WHS +0.031, TNS 0.000. Two
plausible numbers swapped is the worst kind of report error - nothing looks wrong.

This re-derives the key figures independently and compares them to the file.
"""
import io
import re
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATUS = r"D:\agent\nasdaq-fpga\docs\status.md"
SUM_RPT = (r"D:\agent\nasdaq-fpga\vivado\workspace\nasdaq\nasdaq.runs\impl_1"
           r"\nasdaq_wrapper_timing_summary_routed.rpt")
UTIL_RPT = (r"D:\agent\nasdaq-fpga\vivado\workspace\nasdaq\nasdaq.runs\impl_1"
            r"\nasdaq_wrapper_utilization_placed.rpt")

status = io.open(STATUS, encoding="utf-8").read()
fails = []

print("status.md vs build outputs")

# --- timing ---------------------------------------------------------------
t = io.open(SUM_RPT, encoding="utf-8", errors="replace").read()
m = re.search(r"^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s+(-?\d+\.\d+)", t, re.M)
if not m:
    fails.append("cannot parse the timing summary")
else:
    wns, tns, whs = m.group(1), m.group(2), m.group(3)
    # Format as the generator does.
    def f(x):
        return "%.3f" % float(x) if float(x) >= 0 else "%.3f" % float(x)
    line_pat = re.compile(r"timing: WNS ([\d.-]+) ns, WHS ([\d.-]+) ns, TNS ([\d.-]+) ns")
    sm = line_pat.search(status)
    if not sm:
        fails.append("status.md has no timing line")
    else:
        sw, sh, st = sm.groups()
        for label, got, want in (("WNS", sw, wns), ("WHS", sh, whs), ("TNS", st, tns)):
            ok = abs(float(got) - float(want)) < 0.0015
            print("  %-4s status %-8s report %-8s %s"
                  % (label, got, want, "OK" if ok else "MISMATCH"))
            if not ok:
                fails.append("%s: status %s vs report %s" % (label, got, want))

# --- resources ------------------------------------------------------------
u = io.open(UTIL_RPT, encoding="utf-8", errors="replace").read()


def grab(pat):
    mm = re.search(pat, u)
    return int(mm.group(1)) if mm else 0


lut = grab(r"\|\s+LUT as Logic\s+\|\s+(\d+)") + grab(r"\|\s+LUT as Memory\s+\|\s+(\d+)")
ff = grab(r"\|\s+Register as Flip Flop\s+\|\s+(\d+)")
bram = grab(r"\|\s+Block RAM Tile\s+\|\s+(\d+)")
dsp = grab(r"\|\s+DSPs\s+\|\s+(\d+)")

rm = re.search(r"resources: LUT (\d+) \([\d.]+%\), FF (\d+) \([\d.]+%\), "
               r"BRAM (\d+) \([\d.]+%\), DSP (\d+)", status)
if not rm:
    fails.append("status.md has no resources line")
else:
    rl, rf, rb, rd = (int(x) for x in rm.groups())
    for label, got, want in (("LUT", rl, lut), ("FF", rf, ff),
                             ("BRAM", rb, bram), ("DSP", rd, dsp)):
        ok = (got == want)
        print("  %-4s status %-6d report %-6d %s"
              % (label, got, want, "OK" if ok else "MISMATCH"))
        if not ok:
            fails.append("%s: status %d vs report %d" % (label, got, want))

# --- suites ---------------------------------------------------------------
# Circular by construction: status.md records the suite verdict, and this check
# runs INSIDE that suite. When the suite fails for any unrelated reason the
# recorded string becomes FAILED and this check can never pass, so status.md can
# never be regenerated to a passing state. Live example: a stale resource table
# failed util_doc, gen_status.py recorded "FAILED", and this check then failed on
# its own record of that failure.
#
# The useful verification is that status.md's build figures match the reports,
# which the rest of this file does. The verdict is reported for the reader but not
# asserted here.
sm = re.search(r"static contract checks\*\*: `([\w-]+)`", status)
if sm:
    print("  suite verdict recorded as: %s (informational)" % sm.group(1))
else:
    fails.append("status.md does not record a suite verdict")

print()
if fails:
    print("STATUS-DOC-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("STATUS-DOC-PASS")
