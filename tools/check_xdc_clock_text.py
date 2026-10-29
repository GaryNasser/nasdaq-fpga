"""Fail if the constraint file describes a clock frequency other than the real one.

timing_mcyc.xdc described the design clock as 200 MHz long after the design moved to
190 MHz. Five separate comments stated 200 MHz as the current clock while the
multicycle justification referred to 5 ns periods and a 45 ps miss - figures computed
for a period the design no longer has.

That matters because the file's whole purpose is to justify RELAXING timing checks. A
reader deciding whether an exception is still warranted needs the real period. With a
stale figure they cannot tell whether "misses by 45 ps" is still true - and 45 ps is
smaller than the 263 ps of slack the slower clock provides, so at 190 MHz the path may
not need the exception at all.

The check: every "N MHz" in the file must either equal the design clock, or appear in a
sentence that marks it as historical ("original", "was", "target", "measured when",
"figure above"). The design clock is read from the driver's PL_CLK_MHZ, the same source
`check_artifacts` uses, so the two cannot disagree.
"""
import io
import os
import re
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

XDC = r"D:\agent\nasdaq-fpga\vivado\timing_mcyc.xdc"
DRV = r"D:\agent\nasdaq-fpga\board\load_overlay.py"

if not os.path.exists(XDC):
    print("CLOCK-TEXT-FAIL (no constraint file)")
    sys.exit(1)

m = re.search(r"PL_CLK_MHZ\s*=\s*([\d.]+)",
              io.open(DRV, encoding="utf-8").read())
design = float(m.group(1))

# The PS-side clock is legitimately different and must be allowed.
PS_CLOCKS = {100.0}

HISTORICAL = re.compile(r"(original|was |were |target|measured when|figure above|"
                        r"earlier|previously|at the time)", re.I)

lines = io.open(XDC, encoding="latin-1").read().split("\n")

fails = []
checked = 0
print("clock frequencies stated in timing_mcyc.xdc")
print("  design clock (PL_CLK_MHZ): %.3f MHz" % design)
print()

for i, line in enumerate(lines):
    for mm in re.finditer(r"(\d{2,4}(?:\.\d+)?)\s*MHz", line):
        val = float(mm.group(1))
        checked += 1
        if abs(val - design) < 0.5 or val in PS_CLOCKS:
            status = "ok"
        elif HISTORICAL.search(line):
            status = "ok (historical)"
        else:
            status = "STALE"
            fails.append((i + 1, val, line.strip()))
        print("  L%-4d %7.1f MHz  %-16s %s"
              % (i + 1, val, status, line.strip()[:52]))

print()
print("%d frequency mention(s) examined" % checked)
if checked == 0:
    print("CLOCK-TEXT-FAIL (no MHz mentions found - pattern may be stale)")
    sys.exit(1)
if fails:
    print("CLOCK-TEXT-FAIL (%d)" % len(fails))
    for ln, val, text in fails:
        print("  L%d: %.1f MHz stated as current, design is %.1f MHz"
              % (ln, val, design))
    sys.exit(1)
print("CLOCK-TEXT-PASS")
