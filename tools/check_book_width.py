"""Does the driver read each book register with the width the RTL declares?

The RTL exposes twelve counters plus CTRL. `check_book_regmap` verifies the ADDRESSES match. **Nothing verified the
width**, and the driver reads everything through `MMIO(base, 64)` at 4-byte stride, so it always receives 32 bits -
if the RTL drove a narrower register, the high bits would read as whatever was there.

This reads each declaration and each concatenation, and prints the width it found rather than a question mark.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch", "order_book.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

text = io.open(RTL, encoding="utf-8", errors="replace").read()

mux = {}
for m in re.finditer(r"ADDR_(\w+):\s*r_data\s*<=\s*([^;]+);", text):
    mux[m.group(1)] = m.group(2).strip()


def width_of(expr):
    """Return (width, how) or (None, reason)."""
    expr = expr.strip()

    # {N'b0..., ident}
    m = re.match(r"^\{\s*(\d+)'([bdh])[0-9a-fA-F_]+\s*,\s*(\w+)\s*\}$", expr)
    if m:
        pad = int(m.group(1))
        ident = m.group(3)
        d = re.search(r"(?:reg|wire)\s*\[(\d+):0\]\s+%s\b" % re.escape(ident), text)
        if d:
            return pad + int(d.group(1)) + 1, "%d pad + %s[%s:0]" % (pad, ident, d.group(1))
        # A declaration with no range is one bit wide: `reg enable;`
        if re.search(r"(?:reg|wire)\s+%s\s*;" % re.escape(ident), text):
            return pad + 1, "%d pad + %s (1 bit)" % (pad, ident)
        return None, "%s has no declaration" % ident

    # A plain identifier
    if re.match(r"^\w+$", expr):
        d = re.search(r"(?:reg|wire)\s*\[(\d+):0\]\s+%s\b" % re.escape(expr), text)
        if d:
            return int(d.group(1)) + 1, "%s[%s:0]" % (expr, d.group(1))
        if re.search(r"(?:reg|wire)\s+%s\s*;" % re.escape(expr), text):
            return 1, "%s (1 bit)" % expr
        return None, "%s has no declaration" % expr

    return None, "unrecognised form"


print("%-12s %-6s %s" % ("register", "width", "how"))
print("-" * 58)
fails = []
for name, expr in mux.items():
    w, how = width_of(expr)
    flag = "" if w == 32 else "   *** not 32 bits ***"
    print("%-12s %-6s %s%s" % (name, w if w else "?", how[:34], flag))
    if w != 32:
        fails.append((name, w, how))

print()
if fails:
    print("BOOK-WIDTH-FAIL (%d register(s) the driver would read at the wrong width)" % len(fails))
    for n, w, how in fails:
        print("  %-12s width %s (%s)" % (n, w, how))
    sys.exit(1)

print("BOOK-WIDTH-PASS (%d registers, all 32 bits, each width shown above)" % len(mux))
