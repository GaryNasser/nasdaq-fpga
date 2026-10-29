"""Verify the bit and hwh are a matched pair from the same build.

PYNQ loads the .bit and resolves IP addresses from the .hwh. If they come from
different builds the overlay either fails to load, or loads and reads the wrong
registers - which looks like broken RTL.

The first version of this check compared the bitstream's design name against the
hwh's system name and reported a mismatch:

    bit design  : nasdaq_wrapper
    hwh system  : nasdaq

That is not a defect. create_project.tcl line 320 sets `top nasdaq_wrapper`, and
the wrapper instantiates the block design, which is named `nasdaq`. The two names
differ by construction, so comparing them proves nothing either way.

What actually matters for a matched pair:

  * the same part/device;
  * every IP the driver looks up present in the hwh;
  * (already covered elsewhere) IP base addresses matching the RTL decode, and a
    bitstream newer than the RTL it was built from.

This checks the parts and the IP inventory, and reports the design/wrapper names
as information rather than as a failure condition.
"""
import io
import re
import sys

OUT = r"D:\agent\nasdaq-fpga\vivado/out"
BIT = OUT + r"\nasdaq.bit"
HWH = OUT + r"\nasdaq.hwh"

b = open(BIT, "rb").read()
hlen = (b[2] << 8) | b[3]
hdr = b[4:4 + hlen]
h = io.open(HWH, "rb").read().decode("latin-1")

fails = []

print("bitstream header")
m = re.search(rb"nasdaq[a-z_0-9]*", hdr)
bit_design = m.group().decode() if m else None
m = re.search(rb"7z020[a-z0-9]*", hdr)
bit_part = m.group().decode() if m else None
print("  top-level module : %s" % bit_design)
print("  part             : %s" % bit_part)

print()
print("handoff")
m = re.search(r'<SYSTEMINFO[^>]*NAME="([^"]+)"', h)
hwh_sys = m.group(1) if m else None
m = re.search(r'<SYSTEMINFO[^>]*DEVICE="([^"]+)"', h)
hwh_dev = m.group(1) if m else None
print("  block design     : %s" % hwh_sys)
print("  device           : %s" % hwh_dev)
print("  size             : %d bytes" % len(h))
print()
print("  (the bitstream names the top module `nasdaq_wrapper`; the hwh names the")
print("   block design `nasdaq`. They differ by construction - the wrapper")
print("   instantiates the BD - so this is informational, not a mismatch.)")

print()
if bit_part and hwh_dev:
    ok = hwh_dev in bit_part
    print("part/device agree: %s (%s contains %s)"
          % ("YES" if ok else "NO", bit_part, hwh_dev))
    if not ok:
        fails.append("bit part %s vs hwh device %s" % (bit_part, hwh_dev))

print()
print("IP inventory")
for ip in ("mold64_reasm_0", "itch_parse_0", "order_book_0", "ts_hist_0",
           "axi_dma_0"):
    present = ip in h
    print("  %-16s %s" % (ip, "OK" if present else "MISSING"))
    if not present:
        fails.append("hwh lost %s" % ip)

print()
if fails:
    print("BIT-HWH-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("BIT-HWH-PASS")
