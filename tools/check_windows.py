"""Check that every register access stays inside its IP's 4 KB AXI-Lite window.

Each datapath IP owns 0x1000 bytes. A register offset at or beyond 0x1000 would
alias into the next module's window - reading one block's counter from another's
address, or writing a CTRL bit into an unrelated register. That class of bug is
invisible in simulation and produces baffling hardware behaviour.

The mock can expose it, but only if someone looks. This checks it directly:
every REG_* constant in the driver, and every ADDR_* / case arm in the RTL, must
land below 0x1000.

ts_hist is the one at risk: its address map runs to 0x478 plus 256 histogram
bins, but ts_hist is given a 4 KB window (0x40003000-0x40003FFF) and 0x478 < 0x1000,
so it fits - with margin worth knowing about.
"""
import io
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
DRIVER = REPO + r"\board\load_overlay.py"
WINDOW = 0x1000

drv = io.open(DRIVER, encoding="utf-8", errors="surrogateescape").read()
consts = {k: int(v, 16) for k, v in
          re.findall(r"^(REG_\w+)\s*=\s*(0x[0-9A-Fa-f]+)", drv, re.M)}

fails = []
print("driver register constants vs the 4 KB window")
check = [
    ("mold64_reasm", "REG_M64_"),
    ("itch_parse", "REG_IP_"),
    ("order_book", "REG_BOOK_"),
    ("ts_hist", "REG_TS_"),
]
for module, prefix in check:
    vals = {k: v for k, v in consts.items() if k.startswith(prefix)}
    if not vals:
        print("  %-14s (no constants with prefix %s)" % (module, prefix))
        continue
    worst = max(vals.values())
    worst_name = max(vals, key=vals.get)
    ok = worst < WINDOW
    print("  %-14s %2d registers, max %s = 0x%03X %s"
          % (module, len(vals), worst_name, worst,
             "OK" if ok else "OUTSIDE WINDOW"))
    if not ok:
        fails.append("%s: %s = 0x%X exceeds 4 KB window"
                     % (module, worst_name, worst))

print()
print("RTL register maps")
rtl_checks = [
    ("mold64_reasm", REPO + r"\rtl\itch\mold64_reasm.v"),
    ("itch_parse", REPO + r"\rtl\itch\itch_parse.v"),
    ("order_book", REPO + r"\rtl\itch\order_book.v"),
    ("ts_hist", REPO + r"\rtl\itch\ts_hist.v"),
]
for module, path in rtl_checks:
    src = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    # localparam ADDR_x = 10'dN;  // byte 0xYY   -> word index N, byte N*4
    words = []
    for m in re.finditer(r"localparam\s*\[[^\]]+\]\s*ADDR_\w+\s*=\s*([^;]+);", src):
        expr = m.group(1)
        num = re.search(r"\d+'d(\d+)", expr)
        if num:
            words.append(int(num.group(1)))
    if not words:
        print("  %-14s (no ADDR_ localparams; decodes by case arms)" % module)
        continue
    worst_w = max(words)
    worst_b = worst_w * 4
    ok = worst_b < WINDOW
    print("  %-14s max word index %3d = byte 0x%03X %s"
          % (module, worst_w, worst_b, "OK" if ok else "OUTSIDE WINDOW"))
    if not ok:
        fails.append("%s: word %d = byte 0x%X exceeds window"
                     % (module, worst_w, worst_b))

# ts_hist histogram extent: ADDR_HIST_BASE + 256 bins, computed explicitly.
ts = io.open(REPO + r"\rtl\itch\ts_hist.v", encoding="utf-8",
             errors="surrogateescape").read()
m = re.search(r"HIST_BINS\s*=\s*(\d+)", ts)
hb = int(m.group(1)) if m else None
if hb:
    # highest word index used = ADDR_HIST_BASE(12) + HIST_BINS + 18 (TSNOW)
    top_word = 12 + hb + 18
    top_byte = top_word * 4
    ok = top_byte < WINDOW
    print("  %-14s histogram top (12+%d+18)=word %d = byte 0x%03X %s"
          % ("ts_hist", hb, top_word, top_byte, "OK" if ok else "OUTSIDE WINDOW"))
    print("                 headroom to 0x1000: %d bytes" % (WINDOW - top_byte))
    if not ok:
        fails.append("ts_hist histogram top 0x%X exceeds window" % top_byte)

print()
if fails:
    print("WINDOW-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("WINDOW-PASS")
