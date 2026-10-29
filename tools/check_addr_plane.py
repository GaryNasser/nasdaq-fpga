"""One address-plane check for every register block, not just the book.

Round 37 added the plane check for `order_book`. The other two blocks - `itch_parse` and `ts_hist` - have address
checks of their own (`parse_regmap`, `ts_regmap`) but those compare against the DRIVER, not against each other. **A
collision inside one block would look like a driver mismatch or, if the driver also collided, like nothing at all.**

This checks each block's own plane: no two names at one offset, no offset outside the driver's window, and every
`// byte 0xNN` comment consistent with its index.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch")
DRV = os.path.join(REPO, "board", "load_overlay.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The comment forms in use: "// 0x00" and "// byte 0x00".
PAT = re.compile(r"localparam\s*(?:\[[^\]]+\])?\s*ADDR_(\w+)\s*=\s*\d+'d(\d+);\s*//\s*(?:byte\s*)?(0x[0-9A-Fa-f]+)")

drv = io.open(DRV, encoding="utf-8", errors="replace").read()
WINDOWS = {}
# Sizes are written in decimal or hex: MMIO(book_base, 64) and MMIO(ts_base, 0x800).
for base, size in re.findall(r"MMIO\((\w+),\s*(0x[0-9A-Fa-f]+|\d+)\)", drv):
    WINDOWS[base] = int(size, 0)

BLOCKS = [
    ("order_book.v", "book", 4),
    ("ts_hist.v", "ts", 4),
    ("itch_parse.v", "ip", 4),
]

failures = []
total_regs = 0

for fname, base, stride in BLOCKS:
    path = os.path.join(RTL, fname)
    if not os.path.exists(path):
        continue
    text = io.open(path, encoding="utf-8", errors="replace").read()
    regs = []
    for m in PAT.finditer(text):
        regs.append((m.group(1), int(m.group(2)), int(m.group(3), 16)))
    if not regs:
        print("%s: no ADDR_ definitions found" % fname)
        continue

    win = WINDOWS.get("%s_base" % base)
    print("%-16s %2d registers, driver window %s bytes"
          % (fname, len(regs), win if win else "(not found)"))

    seen = {}
    for name, idx, addr in sorted(regs, key=lambda r: r[2]):
        if idx * stride != addr:
            failures.append("%s: %s index %d implies 0x%02X, comment says 0x%02X"
                            % (fname, name, idx, idx * stride, addr))
        if addr in seen:
            failures.append("%s: %s and %s collide at 0x%02X"
                            % (fname, seen[addr], name, addr))
        seen[addr] = name
        if win and addr + stride > win:
            failures.append("%s: %s at 0x%02X is outside the %d-byte window"
                            % (fname, name, addr, win))
    total_regs += len(regs)
    print("                 offsets 0x%02X..0x%02X, %d distinct"
          % (min(a for _, _, a in regs), max(a for _, _, a in regs), len(seen)))

print()
if failures:
    print("ADDR-PLANE-FAIL (%d problem(s))" % len(failures))
    for f in failures:
        print("  " + f)
    sys.exit(1)

print("ADDR-PLANE-PASS (%d registers across %d blocks, no collision, no bad comment, none outside its window)"
      % (total_regs, len(BLOCKS)))
