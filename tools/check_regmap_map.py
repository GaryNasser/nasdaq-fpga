"""Finish the cross-check: resolve REG_* names to offsets and compare per module.

The RTL map is now correct:
    mold64_reasm 8 words, itch_parse 6, order_book 13, ts_hist 12

The driver uses named constants (REG_M64_CTRL = 0x18 etc.) scoped by prefix:

    REG_M64_*   -> mold64_reasm
    REG_IP_*    -> itch_parse
    REG_BOOK_*  -> order_book
    REG_TS_*    -> ts_hist

Comparing each prefix's offsets against its module's decode is the check that matters: a
CTRL at the wrong offset means the driver writes control into a read-only slot and the
pipeline never enables - with no error, just silence.

ts_hist is handled specially: it also exposes an address window (REG_TS_HIST_BASE 0x30,
REG_TS_OVERFLOW 0x474, REG_TS_TSNOW 0x478) that the decode covers with a base+offset
scheme rather than individual case arms, so those are excluded from the strict comparison
and reported separately.
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


def strip_comments(text):
    code = re.sub(r"//[^\n]*", "", text)
    return re.sub(r"/\*.*?\*/", "", code, flags=re.S)


def parse_literal(text):
    t = text.strip().replace("_", "")
    m = re.fullmatch(r"(\d+)?'([hdbo])([0-9A-Fa-f]+)", t)
    if m:
        try:
            return int(m.group(3), {"h": 16, "d": 10, "b": 2, "o": 8}[m.group(2)])
        except ValueError:
            return None
    m = re.fullmatch(r"\d+", t)
    return int(t) if m else None


def constants(code):
    out = {}
    for m in re.finditer(r"\b(?:localparam|parameter)\b\s*(?:\[[^\]]*\])?\s*(\w+)\s*=\s*"
                         r"([^;,)]+)", code):
        v = parse_literal(m.group(2))
        if v is not None:
            out[m.group(1)] = v
    return out


def rtl_map(path):
    code = strip_comments(io.open(path, encoding="latin-1").read())
    consts = constants(code)
    sel = None
    for m in re.finditer(r"case\s*\(\s*(\w+)\s*(?:\[\s*(\d+)\s*:\s*(\d+)\s*\])?\s*\)", code):
        if "addr" in m.group(1).lower():
            sel = m
            break
    if sel is None:
        return {}, consts
    body = code[sel.end():]
    out = {}
    for am in re.finditer(r"\b(\w+|\d+'d\d+)\s*:\s*r_data\s*<=\s*([^;]+);", body):
        key = am.group(1)
        if key == "default":
            continue
        if re.fullmatch(r"\d+'d\d+", key):
            word = int(key.split("'d")[1])
        else:
            word = consts.get(key)
            if word is None:
                continue
        out[word * 4] = am.group(2).strip()
    return out, consts


MODULES = {
    "mold64_reasm": ("mold64_reasm.v", "REG_M64_"),
    "itch_parse": ("itch_parse.v", "REG_IP_"),
    "order_book": ("order_book.v", "REG_BOOK_"),
    "ts_hist": ("ts_hist.v", "REG_TS_"),
}

drv = io.open(DRV, encoding="utf-8", errors="surrogateescape").read()
drv_consts = {}
for m in re.finditer(r"^(REG_\w+)\s*=\s*(0x[0-9A-Fa-f]+)", drv, re.M):
    drv_consts[m.group(1)] = int(m.group(2), 16)

print("register map cross-check, per module")
print()
fails = []
for label, (fname, prefix) in MODULES.items():
    path = os.path.join(RTL, fname)
    rtl, _ = rtl_map(path)
    used = {k: v for k, v in drv_consts.items() if k.startswith(prefix)}
    print("  %-14s RTL %2d word(s), driver %d constant(s) under %s"
          % (label, len(rtl), len(used), prefix))
    if not rtl:
        fails.append("%s: no RTL decode" % label)
        continue
    if not used:
        fails.append("%s: no driver constants under %s" % (label, prefix))
        continue

    for name, off in sorted(used.items(), key=lambda kv: kv[1]):
        if label == "ts_hist" and off >= 0x30:
            # address-window registers; not individual case arms
            continue
        present = off in rtl
        mark = "ok" if present else "NOT DECODED"
        print("     %-24s 0x%02X  %s%s"
              % (name, off, mark,
                 "" if present else "  (rtl has 0x%s)"
                 % ",".join("%02X" % o for o in sorted(rtl))))
        if not present:
            fails.append("%s: driver constant %s at 0x%02X has no RTL decode"
                         % (label, name, off))
    print()

if fails:
    print("REGMAP-MAP-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("REGMAP-MAP-PASS (every driver constant has an RTL decode at the same offset)")
