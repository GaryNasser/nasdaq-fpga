"""Fail if the block design's clock topology stops matching what the report claims.

The measured topology (round 35):

    clk_200m -> ps7_0/M_AXI_GP0_ACLK and every axi_interconnect_0 ACLK
    fclk0    -> ps7_0's S_AXI_*_ACLK and axi_mem_intercon/M00_ACLK

from which two things follow that the report now states:

  * the GP0 control plane is single-domain, so its false_path exemptions are about
    protocol timing and not a clock crossing;
  * the only crossing is axi_mem_intercon S00 <-> M00, backed by auto_cc.

Both are claims about a source file, so they can be re-derived cheaply. If someone
later moves a connection - gives axi_interconnect_0 a second clock, or re-points
M_AXI_GP0_ACLK at fclk0 - the design gains a CDC that the report does not mention, and
the asynchronous clock group would hide it.

This check re-derives the topology from the BD connections and asserts:

  * axi_interconnect_0 is driven by exactly ONE clock net;
  * ps7_0/M_AXI_GP0_ACLK uses that same net;
  * axi_mem_intercon has two clock nets (it is the designated crossing).
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

TCL = r"D:\agent\nasdaq-fpga\vivado\create_project.tcl"

if not os.path.exists(TCL):
    print("CDC-MAP-FAIL (no block design source)")
    sys.exit(1)

src = io.open(TCL, encoding="utf-8", errors="replace").read()

# Join continuations, strip comments so prose cannot inject connections.
joined = []
buf = ""
for l in src.split("\n"):
    s = l.split("#")[0].rstrip()
    if not s:
        continue
    if s.endswith("\\"):
        buf += s[:-1] + " "
        continue
    joined.append(buf + s)
    buf = ""

# Map instance -> set of clock nets its ACLK pins see.
aclocks = {}
for l in joined:
    m = re.match(r"\s*connect_bd_net\s+-net\s+(\S+)\s+(.*)", l)
    if not m:
        continue
    net, rest = m.group(1), m.group(2)
    for inst, port in re.findall(r"get_bd_pins\s+(\S+)/(\w*ACLK\w*)", rest):
        aclocks.setdefault(inst, set()).add(net)

print("clock nets per instance (from BD connections)")
for inst in sorted(aclocks):
    print("  %-22s %s" % (inst, sorted(aclocks[inst])))
print()

fails = []

ic = aclocks.get("axi_interconnect_0", set())
if len(ic) != 1:
    fails.append("axi_interconnect_0 sees %d clock nets: %s" % (len(ic), sorted(ic)))
else:
    print("  axi_interconnect_0 single-domain: %s" % sorted(ic))

ps = aclocks.get("ps7_0", set())

# Which net drives M_AXI_GP0_ACLK?
# LAST assignment wins: a later connect_bd_net overrides an earlier one. Taking the
# first match missed a re-pointing - found by mutation, which appended fclk0 and the
# check still reported clk_200m.
gp0 = None
for l in joined:
    m = re.match(r"\s*connect_bd_net\s+-net\s+(\S+)\s+(.*)", l)
    if m and "ps7_0/M_AXI_GP0_ACLK" in m.group(2):
        gp0 = m.group(1)
print("  ps7_0/M_AXI_GP0_ACLK net: %s" % gp0)

if ic and gp0 and gp0 not in ic:
    fails.append("GP0 ACLK (%s) is not axi_interconnect_0's clock (%s) - a CDC now "
                 "exists on the control plane" % (gp0, sorted(ic)))

mem = aclocks.get("axi_mem_intercon", set())
print("  axi_mem_intercon clock nets: %s" % sorted(mem))
if len(mem) < 2:
    fails.append("axi_mem_intercon no longer spans two clocks - the documented "
                 "crossing is gone, and the async group may now hide something else")

print()
if len(aclocks) == 0:
    print("CDC-MAP-FAIL (no ACLK assignments parsed)")
    sys.exit(1)
if fails:
    print("CDC-MAP-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("CDC-MAP-PASS (topology matches the documented one)")
