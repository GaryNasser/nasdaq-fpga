"""Every itch_parse register must match the driver's REG_IP_* offsets.

`itch_parse` declares six registers; the driver names the same six as `REG_IP_*`.

    RTL:    localparam ADDR_PARSE_CNT_LO = 3'd0;  // 0x00
    driver: REG_IP_PARSE_CNT_LO = 0x00

`audit_groups` showed `IP` has no dedicated comparison - the checks that name it (`check_regmap`) cover a different
prefix. So this is the same gap round 240 closed for `TS`, in the block that counts parsed messages.

**The prefix differs (IP vs PARSE), so a naive same-name match would find nothing.** The mapping is positional:
every `ADDR_X` in `itch_parse.v` must have `REG_IP_X` in the driver at index*4.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch", "itch_parse.v")
DRV = os.path.join(REPO, "board", "load_overlay.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

rtl_src = io.open(RTL, encoding="latin-1").read()
drv_src = io.open(DRV, encoding="utf-8", errors="replace").read()

# ADDR_NAME = <width>'d<index>;   // 0xNN
rtl = {}
self_inconsistent = []
for m in re.finditer(r"ADDR_(\w+)\s*=\s*(\d+)'d(\d+)\s*;\s*//\s*0x([0-9A-Fa-f]+)", rtl_src):
    name, index, byte = m.group(1), int(m.group(3)), int(m.group(4), 16)
    rtl[name] = byte
    if index * 4 != byte:
        self_inconsistent.append((name, index, byte))

drv = {m.group(1): int(m.group(2), 16)
       for m in re.finditer(r"REG_IP_(\w+)\s*=\s*(0x[0-9A-Fa-f]+)", drv_src)}

print("itch_parse ADDR_* registers : %d" % len(rtl))
print("driver REG_IP_* constants   : %d" % len(drv))
print()

if self_inconsistent:
    print("RTL index does not match its own byte comment:")
    for n, i, b in self_inconsistent:
        print("   %-18s index %d -> byte 0x%02X (index*4 = 0x%02X)" % (n, i, b, i * 4))
    print()

problems = []
for n in sorted(set(rtl) | set(drv)):
    a, b = rtl.get(n), drv.get(n)
    if a is None:
        problems.append((n, "driver-only", None, b))
    elif b is None:
        problems.append((n, "RTL-only", a, None))
    elif a != b:
        problems.append((n, "MISMATCH", a, b))

for n, why, a, b in problems:
    print("  %-18s %-12s RTL %-6s driver %-6s"
          % (n, why, ("0x%02X" % a) if a is not None else "-",
             ("0x%02X" % b) if b is not None else "-"))

agree = len(set(rtl) & set(drv)) - len([p for p in problems if p[1] == "MISMATCH"])
print()
print("agree: %d of %d" % (agree, len(rtl)))

print()
if self_inconsistent or problems:
    print("PARSE-REGMAP-FAIL (%d)" % (len(self_inconsistent) + len(problems)))
    sys.exit(1)
print("PARSE-REGMAP-PASS (all %d itch_parse registers match REG_IP_*)" % len(rtl))
