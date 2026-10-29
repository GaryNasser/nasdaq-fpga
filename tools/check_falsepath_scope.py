"""Fail if the false_path exemptions reach outside the AXI-Lite converter.

The audit (round 34) established, by measurement on the routed build:

    L60  442 pins, ALL under axi_interconnect_0/s00_couplers/auto_pc/
    L73    1 pin, the PS write-ready port
    one-level fan-in of those 442 pins: all in axi_interconnect_0

which is what the file claims. The risk is that this stops being true: a pattern such
as *axi_interconnect_0/* would silently swallow the AXI-MM datapath, and the design
would report a clean WNS measured over fewer paths than exist.

The check is structural and cheap - it reads the pin patterns out of the XDC and
requires each to be anchored inside the converter hierarchy:

  * the -through pattern must contain the auto_pc segment;
  * the -to pattern must name the PS ready port;
  * neither pattern may contain a wildcard broad enough to match a datapath module
    (mold64_reasm, itch_parse, order_book, ts_hist) - checked both as a literal and as
    a too-broad prefix like "nasdaq_i/*".

It cannot prove the fan-in at build time without opening the design; the measurement in
the report is the evidence for that. What it CAN do is stop the patterns drifting into
a form whose scope nobody has measured.
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

if not os.path.exists(XDC):
    print("FALSEPATH-GUARD-SKIPPED (no constraint file)")
    sys.exit(0)

lines = io.open(XDC, encoding="latin-1").read().split("\n")

DATAPATH = ("mold64_reasm", "itch_parse", "order_book", "ts_hist")

# Gather active set_false_path commands with their continuations.
cmds = []
buf = ""
for l in lines:
    s = l.split("#")[0].rstrip()
    if not s:
        continue
    if s.endswith("\\"):
        buf += s[:-1] + " "
        continue
    buf += s
    cmds.append(" ".join(buf.split()))
    buf = ""

fps = [c for c in cmds if c.startswith("set_false_path")]

print("set_false_path scope check")
print("  active set_false_path commands: %d" % len(fps))
print()

fails = []
for c in fps:
    kind = "-through" if "-through" in c else ("-to" if "-to" in c else "?")
    # Extract the NAME =~ pattern.
    m = re.search(r"NAME\s*=~\s*([^\s}\]]+)", c)
    pat = m.group(1) if m else "?"

    problems = []
    if any(d in pat for d in DATAPATH):
        problems.append("pattern names a datapath module")
    # A pattern that starts at the whole design is too broad to have been measured.
    if re.match(r"^nasdaq_i/\*", pat) or pat in ("*", "nasdaq_i/*"):
        problems.append("pattern anchored at the whole design")
    if kind == "-through" and "auto_pc" not in pat:
        problems.append("through-pattern no longer anchored in auto_pc")
    if kind == "-to" and "MAXIGP0WREADY" not in pat:
        problems.append("to-pattern no longer the PS ready port")

    state = "ok" if not problems else "; ".join(problems)
    print("  %-9s %-58s %s" % (kind, pat[:58], state))
    if problems:
        fails.append((kind, pat, problems))

print()
if fails:
    print("FALSEPATH-GUARD-FAIL (%d)" % len(fails))
    for kind, pat, problems in fails:
        print("  %s %s: %s" % (kind, pat, "; ".join(problems)))
    print()
    print("  Measured scope on 2026-10-23: 442 pins, all inside auto_pc; fan-in all")
    print("  in axi_interconnect_0. A broader pattern would exempt paths nobody has")
    print("  measured, and WNS would be reported over fewer paths than exist.")
    sys.exit(1)
print("FALSEPATH-GUARD-PASS")
