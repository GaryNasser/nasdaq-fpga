"""Every order_book register must match the driver's BOOK_REGS offsets.

`itch_parse` and `ts_hist` both have such a check (`check_parse_regmap`, `check_ts_regmap`). **`order_book` had none**,
despite defining thirteen addresses and being the module every published counter comes from.

The driver's BOOK_REGS dictionary is the thing the board actually reads. If an RTL address moves and the dictionary
does not, every board measurement silently reads the wrong register - and the numbers would still look plausible.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RTL = os.path.join(REPO, "rtl", "itch", "order_book.v")
DRV = os.path.join(REPO, "board", "load_overlay.py")

rtl = io.open(RTL, encoding="utf-8", errors="replace").read()
drv = io.open(DRV, encoding="utf-8", errors="replace").read()

# RTL: localparam ADDR_X = 4'dN;  // 0xNN
rtl_regs = {}
for m in re.finditer(r"localparam ADDR_(\w+)\s*=\s*4'd(\d+);\s*//\s*(0x[0-9A-Fa-f]+)", rtl):
    name, idx, hexaddr = m.group(1), int(m.group(2)), m.group(3).upper()
    rtl_regs[name] = (idx, hexaddr)

# The comment and the index must agree - a stale comment is how a reader gets misled.
for name, (idx, hexaddr) in list(rtl_regs.items()):
    if idx * 4 != int(hexaddr, 16):
        print("  %-12s index %d implies 0x%02X but the comment says %s"
              % (name, idx, idx * 4, hexaddr))

# Driver: BOOK_REGS = { 'name': 0xNN, ... }
block = re.search(r"BOOK_REGS\s*=\s*\{(.*?)\}", drv, re.S)
if not block:
    print("BOOK_REGS not found in the driver")
    sys.exit(1)
drv_regs = {}
for m in re.finditer(r"'(\w+)'\s*:\s*(0x[0-9A-Fa-f]+)", block.group(1)):
    drv_regs[m.group(1)] = m.group(2).upper()

print("RTL ADDR_ definitions : %d" % len(rtl_regs))
print("driver BOOK_REGS      : %d" % len(drv_regs))
print()
print("%-16s %-6s %-8s %-8s %s" % ("register", "rtl#", "rtl hex", "driver", "verdict"))
print("-" * 62)

fails = []
# The driver keys are lower-case with the same stem; RTL uses upper snake.
for name, (idx, hexaddr) in sorted(rtl_regs.items(), key=lambda kv: kv[1][0]):
    key = name.lower()
    d = drv_regs.get(key)
    if d is None:
        verdict = "not in the driver"
        if name != "CTRL":       # CTRL is a constant, not a member of BOOK_REGS
            print("%-16s %-6d %-8s %-8s %s" % (name, idx, hexaddr, "-", verdict))
        continue
    ok = d == hexaddr
    print("%-16s %-6d %-8s %-8s %s" % (name, idx, hexaddr, d, "match" if ok else "*** MISMATCH ***"))
    if not ok:
        fails.append((name, hexaddr, d))

# Any driver entry with no RTL counterpart is a stale read.
for key, addr in sorted(drv_regs.items()):
    if key.upper() not in rtl_regs:
        print("%-16s %-6s %-8s %-8s *** driver reads a register the RTL does not define ***"
              % (key.upper(), "-", "-", addr))
        fails.append((key, None, addr))

print()
if fails:
    print("BOOK-REGMAP-FAIL (%d disagreement(s))" % len(fails))
    for f in fails:
        print("  %s" % (f,))
    sys.exit(1)

print("BOOK-REGMAP-PASS (%d order_book registers agree with the driver's BOOK_REGS)" % len(drv_regs))
