"""Every design-clock claim in create_project.tcl must match the configured frequency.

`create_project.tcl` used to say 200 MHz in several places and configure 190.

    L5    #   ps7_0 (official PYNQ-Z2 PS config, design clock 200 MHz)
    L14   #   + clk_wiz_0 (100 -> 200 MHz)
    L47   # seeds and the design is marginal at 200 MHz.
    ...
    set_property -dict [list CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {190.000} ...

**The code is right (190) and the prose is stale (200).** The design was moved to 190 to close timing, and the
header comments were not updated.

### Why a stale comment here is worth fixing rather than tolerating

Every figure in the report is at 190 MHz. **A maintainer reading this file's header would take 200 as the design
clock** and compute cycles-per-second wrongly - and the report has already had one round (206) where a figure was
attributed to the wrong build.

The check: **any "N MHz" in the file's comments must match CLKOUT1_REQUESTED_OUT_FREQ.**
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TCL = os.path.join(REPO, "vivado", "create_project.tcl")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(TCL, encoding="utf-8", errors="replace").read()
lines = src.split("\n")

m = re.search(r"CLKOUT1_REQUESTED_OUT_FREQ\s*\{([\d.]+)\}", src)
if not m:
    print("CLOCK-DOC-FAIL (no CLKOUT1_REQUESTED_OUT_FREQ in the file)")
    sys.exit(1)
configured = float(m.group(1))
print("CLKOUT1_REQUESTED_OUT_FREQ = %.3f MHz" % configured)
print()

# Only comments that ASSERT a clock, not every frequency mention.
CLAIM = re.compile(
    r"(?:design clock|everything runs at|clk_wiz_0 \(\s*\d+\s*->|the (?:[\d.]+)\s*MHz clk_out1)"
    r"\D{0,12}([\d.]+)\s*MHz", re.I)
# Also: "-> N MHz design clock" and "the N MHz clk_out1" without a leading article.
CLAIM2 = re.compile(r"->\s*([\d.]+)\s*MHz design clock|the\s*([\d.]+)\s*MHz clk_out1", re.I)

bad = []
all_mentions = []
for i, l in enumerate(lines):
    _code, _, comment = l.partition("#")
    for mm in list(CLAIM.finditer(comment)) + list(CLAIM2.finditer(comment)):
        val = float(mm.group(1) if mm.group(1) else mm.group(2))
        all_mentions.append((i + 1, val, l.strip()[:78]))
        if abs(val - configured) > 0.5:
            bad.append((i + 1, val, l.strip()[:78]))

print("clock CLAIMS in comments: %d" % len(all_mentions))
for ln, val, txt in all_mentions:
    mark = "" if abs(val - configured) <= 0.5 else "   <-- not the configured clock"
    print("  L%-5d %6.1f%s" % (ln, val, mark))
    if mark:
        print("         %s" % txt)

print()
if bad:
    print("CLOCK-DOC-FAIL (%d stale clock mention(s))" % len(bad))
    sys.exit(1)
print("CLOCK-DOC-PASS (every MHz in the comments matches the configured %.1f MHz)" % configured)
