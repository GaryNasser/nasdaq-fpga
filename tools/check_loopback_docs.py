"""Fail if the driver advertises a mode the block design cannot support.

`--loopback` requires the `loopback_dma` IP. The current block design does not contain
it - `create_project.tcl` never instantiates one - so the mode is guaranteed to exit 4.

Its help text used to say only "M1: DMA loopback test", which invites the reader to
conclude the bitstream is broken when it fails. Two lines now say otherwise.

This check couples the two facts that must stay consistent:

  * if the BD has no loopback_dma, the CLI must say the mode is unavailable;
  * if the BD DOES gain one, the warning is stale and should be removed.

Same for any other IP the driver looks up by name: the driver's `find_ip` calls are the
list of what it needs, and the BD is the list of what exists.

The cross-reference is deliberately narrow - it checks `loopback_dma` because that is
the one known divergence. A general "every find_ip must exist in the BD" rule would flag
`axi_dma` on overlays where it is legitimately absent.
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

REPO = r"D:\agent\nasdaq-fpga"
DRV = os.path.join(REPO, "board", "load_overlay.py")
TCL = os.path.join(REPO, "vivado", "create_project.tcl")

for p in (DRV, TCL):
    if not os.path.exists(p):
        print("LOOPBACK-DOC-FAIL (missing %s)" % os.path.basename(p))
        sys.exit(1)

drv = io.open(DRV, encoding="utf-8").read()
tcl = io.open(TCL, encoding="utf-8", errors="replace").read()

bd_has = "loopback_dma" in tcl
help_says_unavailable = "NOT available on this overlay" in drv
msg_says_needs_m1 = "needs the M1 loopback overlay" in drv

print("--loopback consistency")
print()
print("  block design instantiates loopback_dma : %s" % bd_has)
print("  help text warns it is unavailable      : %s" % help_says_unavailable)
print("  failure message explains why           : %s" % msg_says_needs_m1)
print()

fails = []
if not bd_has and not help_says_unavailable:
    fails.append("--loopback is unavailable but the help text does not say so")
if not bd_has and not msg_says_needs_m1:
    fails.append("the runtime failure does not explain that loopback_dma is M1-only")
if bd_has and help_says_unavailable:
    fails.append("the BD now has loopback_dma but the help still says unavailable")

if fails:
    print("LOOPBACK-DOC-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("LOOPBACK-DOC-PASS (help matches what the design can do)")
