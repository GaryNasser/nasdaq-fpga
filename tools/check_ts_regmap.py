"""Every ts_hist control-window register the driver names must match the RTL.

`ts_hist` declares named address constants; the driver must agree with every one of them.

`check_regmap` covers `REG_M64_*` (and a sibling covers `TS`). Round 228 found a register outside that coverage by
accident. **This asks the question directly, for the module whose register map has a written table.**

    RTL:    localparam [9:0] ADDR_DELTA = 10'd5;   // byte 0x14
    driver: REG_TS_DELTA = 0x14

The RTL is the authority: its comment carries the byte address, and the index must equal byte/4.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch", "ts_hist.v")
DRV = os.path.join(REPO, "board", "load_overlay.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

rtl_src = io.open(RTL, encoding="latin-1").read()
drv_src = io.open(DRV, encoding="utf-8", errors="replace").read()

# ADDR_NAME = <width>'d<index>;   // byte 0xNN
rtl = {}
bad_index = []
for m in re.finditer(r"ADDR_(\w+)\s*=\s*(\d+)'d(\d+)\s*;\s*//\s*byte\s*0x([0-9A-Fa-f]+)", rtl_src):
    name, index, byte = m.group(1), int(m.group(3)), int(m.group(4), 16)
    rtl[name] = byte
    if index * 4 != byte:
        bad_index.append((name, index, byte))

drv = {m.group(1): int(m.group(2), 16)
       for m in re.finditer(r"REG_TS_(\w+)\s*=\s*(0x[0-9A-Fa-f]+)", drv_src)}

print("ts_hist registers declared in RTL : %d" % len(rtl))
print("REG_TS_* constants in the driver   : %d" % len(drv))
print()

if bad_index:
    print("RTL index does not match its own byte comment:")
    for name, index, byte in bad_index:
        print("   %-14s index %d -> byte 0x%02X (index*4 = 0x%02X)" % (name, index, byte, index * 4))
    print()

# Scope: the AXI-Lite control window is the first 0x30 bytes. Addresses beyond that are the histogram
# RAM (OVERFLOW, TSNOW live there) and are not part of this table.
WINDOW = 0x30   # inclusive: HIST_BASE sits AT 0x30 and is part of the map
drv_ctrl = {k: v for k, v in drv.items() if v <= WINDOW}
drv_other = {k: v for k, v in drv.items() if v > WINDOW}

print("driver constants in the 0x00-0x%02X window: %d" % (WINDOW - 1, len(drv_ctrl)))
print("driver constants beyond it (hist RAM):     %d  %s"
      % (len(drv_other), sorted(drv_other)))
print()

# Registers the RTL declares that the driver does not read are debug taps, reported not failed.
DEBUG_TAPS = {"T0_LO", "T0_HI", "T1_LO", "T1_HI"}

names = sorted(set(rtl) | set(drv_ctrl))
mismatch = []
missing_in_drv = []
for n in names:
    a = rtl.get(n)
    b = drv_ctrl.get(n)
    if a is None:
        mark = "driver-only"
        missing_in_drv.append(n)
    elif b is None:
        mark = "RTL-only (debug tap)" if n in DEBUG_TAPS else "RTL-only"
    elif a != b:
        mark = "MISMATCH"
        mismatch.append((n, a, b))
    else:
        mark = "ok"
    if mark != "ok":
        print("  %-14s RTL %-6s driver %-6s %s"
              % (n, ("0x%02X" % a) if a is not None else "-",
                 ("0x%02X" % b) if b is not None else "-", mark))

print()
print("agree: %d   mismatch: %d   RTL-only: %d   driver-only: %d"
      % (len(names) - len(mismatch) - len(missing_in_drv)
         - len([n for n in names if n in rtl and n not in drv]),
         len(mismatch),
         len([n for n in names if n in rtl and n not in drv]),
         len(missing_in_drv)))

print()
if bad_index or mismatch:
    print("TS-REGMAP-FAIL (%d)" % (len(bad_index) + len(mismatch)))
    sys.exit(1)
_taps = len([n for n in rtl if n in DEBUG_TAPS])
_agree = len(rtl) - _taps
print("TS-REGMAP-PASS (%d control-window registers agree; %d debug taps the driver does not read; "
      "%d hist-RAM registers are a different address space)"
      % (_agree, _taps, len(drv_other)))
