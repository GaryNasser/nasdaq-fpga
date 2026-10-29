"""Cross-check the driver's register constants against the RTL.

Purpose: a register-address mismatch between `board/load_overlay.py` and the RTL
fails only on hardware. With the board unreachable that would surface later as an
unexplained wrong read, so the contract is checked statically instead.

The previous version of this script was itself wrong twice:

  * it required every module to declare `ADDR_*` localparams, but mold64_reasm,
    itch_parse and order_book decode with `case (word_index)` and 3'dN literals,
    so most checks reported MISSING when nothing was missing;
  * it looked for the `// byte 0xXX` comment in the 60 characters *after* the
    constant, which picks up the NEXT line's comment for constants whose own
    comment is short - that produced two bogus MISMATCH results for
    ADDR_OVERFLOW and ADDR_TSNOW, which in fact agree exactly.

This version reads the `// byte 0xXX` comment on the same line as the constant,
and evaluates expression constants (e.g. `12 + HIST_BINS + 17`) numerically.
"""
import io
import re
import sys

DRIVER = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
RTL = {
    "mold64_reasm": r"D:\agent\nasdaq-fpga\rtl\itch\mold64_reasm.v",
    "itch_parse":   r"D:\agent\nasdaq-fpga\rtl\itch\itch_parse.v",
    "order_book":   r"D:\agent\nasdaq-fpga\rtl\itch\order_book.v",
    "ts_hist":      r"D:\agent\nasdaq-fpga\rtl\itch\ts_hist.v",
}

driver = io.open(DRIVER, encoding="utf-8", errors="surrogateescape").read()
consts = {k: int(v, 16) for k, v in
          re.findall(r"^(REG_\w+)\s*=\s*(0x[0-9A-Fa-f]+)", driver, re.M)}


def rtl_constants(path):
    """Return {ADDR_NAME: word_index} plus localparams for numeric deps."""
    src = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    locals_ = {}
    # Plain numeric/expression localparams and parameters we may need.
    for m in re.finditer(r"(?:localparam|parameter)\s*(?:\[[^\]]+\]\s*)?(\w+)\s*=\s*([^;,]+)[;,]", src):
        locals_[m.group(1)] = m.group(2).strip()

    def ev(name, depth=0):
        if depth > 8 or name not in locals_:
            return None
        expr = locals_[name]
        expr = re.sub(r"\d+'d(\d+)", r"\1", expr)
        expr = re.sub(r"\d+'h([0-9A-Fa-f]+)", lambda m: str(int(m.group(1), 16)), expr)
        # Substitute simple identifiers.
        for ident in set(re.findall(r"\b[A-Za-z_]\w*\b", expr)):
            if ident in locals_:
                v = ev(ident, depth + 1)
                if v is None:
                    return None
                expr = re.sub(r"\b%s\b" % ident, str(v), expr)
        if not re.fullmatch(r"[0-9+\-*/() ]+", expr):
            return None
        try:
            return int(eval(expr, {"__builtins__": {}}, {}))
        except Exception:
            return None

    addrs = {}
    for name, expr in locals_.items():
        if name.startswith("ADDR_"):
            v = ev(name)
            if v is not None:
                addrs[name] = v
    return addrs, locals_


parsed = {}
for ip, path in RTL.items():
    addrs, loc = rtl_constants(path)
    parsed[ip] = addrs
    print("%-14s %d ADDR_ constants" % (ip, len(addrs)))

checks = [
    ("ts_hist",      "REG_TS_MIN",        "ADDR_MIN"),
    ("ts_hist",      "REG_TS_MAX",        "ADDR_MAX"),
    ("ts_hist",      "REG_TS_SUM_LO",     "ADDR_SUM_LO"),
    ("ts_hist",      "REG_TS_COUNT_LO",   "ADDR_COUNT_LO"),
    ("ts_hist",      "REG_TS_HIST_BASE",  "ADDR_HIST_BASE"),
    ("ts_hist",      "REG_TS_OVERFLOW",   "ADDR_OVERFLOW"),
    ("ts_hist",      "REG_TS_TSNOW",      "ADDR_TSNOW"),
    ("ts_hist",      "REG_TS_DELTA",      "ADDR_DELTA"),
    ("ts_hist",      "REG_TS_CTRL",       "ADDR_CTRL"),
    ("itch_parse",   "REG_IP_PARSE_CNT_LO", "ADDR_PARSE_CNT_LO"),
    ("itch_parse",   "REG_IP_DROP_LEN_CNT", "ADDR_DROP_LEN_CNT"),
    ("itch_parse",   "REG_IP_ERR_TYPE_CNT", "ADDR_ERR_TYPE_CNT"),
    ("itch_parse",   "REG_IP_STOCK_DIR_CNT", "ADDR_STOCK_DIR_CNT"),
    ("itch_parse",   "REG_IP_CTRL",       "ADDR_CTRL"),
    ("order_book",   "REG_BOOK_CTRL",     "ADDR_CTRL"),
]

print()
print("contract checks (byte address = word index * 4):")
fails = []
for ip, dconst, rconst in checks:
    dval = consts.get(dconst)
    w = parsed[ip].get(rconst)
    if dval is None or w is None:
        fails.append("%s: %s / %s not resolvable" % (ip, dconst, rconst))
        print("  %-12s %-24s driver=%s rtl=%s UNRESOLVED"
              % (ip, dconst, "0x%02X" % dval if dval is not None else "-",
                 "0x%02X" % (w * 4) if w is not None else "-"))
        continue
    rval = w * 4
    ok = (dval == rval)
    print("  %-12s %-24s driver=0x%02X rtl=0x%02X %s"
          % (ip, dconst, dval, rval, "OK" if ok else "MISMATCH"))
    if not ok:
        fails.append("%s %s driver 0x%02X != rtl 0x%02X" % (ip, dconst, dval, rval))

# mold64_reasm decodes with `case (word_index)` and 3'dN literals rather than
# ADDR_ constants, so it needs its own pass over the case arms.
src = io.open(RTL["mold64_reasm"], encoding="utf-8", errors="surrogateescape").read()
arms = {}
for m in re.finditer(r"3'd(\d+):\s*r_data\s*<=\s*[^;]+;\s*//\s*([A-Z_]+)", src):
    arms[int(m.group(1))] = m.group(2)

print()
print("mold64_reasm case-decode contract (byte = index * 4):")
m64 = {"REG_M64_RX_PACKETS_LO": "RX_PACKETS_LO",
       "REG_M64_RX_PACKETS_HI": "RX_PACKETS_HI",
       "REG_M64_RX_MESSAGES_LO": "RX_MESSAGES_LO",
       "REG_M64_RX_MESSAGES_HI": "RX_MESSAGES_HI",
       "REG_M64_GAP_COUNT": "GAP_COUNT",
       "REG_M64_ERROR_COUNT": "ERROR_COUNT",
       "REG_M64_CTRL": "CTRL"}
for dconst, want in m64.items():
    dval = consts.get(dconst)
    if dval is None:
        fails.append("%s missing from driver" % dconst)
        print("  %-24s driver missing" % dconst)
        continue
    got = arms.get(dval // 4)
    ok = (got == want)
    print("  %-24s driver=0x%02X rtl=%-14s %s"
          % (dconst, dval, got or "-", "OK" if ok else "MISMATCH"))
    if not ok:
        fails.append("%s driver 0x%02X != rtl %s" % (dconst, dval, got))

print()
if fails:
    print("REGISTER-CONTRACT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)  # the runner decides PASS from the exit code alone
else:
    print("REGISTER-CONTRACT-PASS")
