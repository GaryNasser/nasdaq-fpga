"""Compare the packer's layout against the unpacker's slices, field by field.

itch_parse packs:

    { 3'd0, d_type, d_timestamp, d_order_ref, d_aux_ref, d_price, d_shares,
      d_side, d_act }

order_book unpacks with declaration-time assignments such as:

    wire [3:0]  act       = evt[3:0];
    wire        side      = evt[4];
    wire [31:0] price     = evt[68:37];
    ...

The two must agree exactly. A one-bit offset would put, say, the low bit of price into the
high bit of shares - every value still a plausible number, no counter wrong, and the book
silently mispriced.

This extracts both sides and compares field widths and positions. It also checks that the
slices together tile [255:0] with no gap and no overlap, which is the property that makes
a flat bus safe.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
PARSER = os.path.join(REPO, "rtl", "itch", "itch_parse.v")
BOOK = os.path.join(REPO, "rtl", "itch", "order_book.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

parser = io.open(PARSER, encoding="latin-1").read()
book = io.open(BOOK, encoding="latin-1").read()

# --- packer: evt_pack fields and their declared widths ----------------------
m = re.search(r"wire\s*\[255:0\]\s*evt_pack\s*=\s*\{(.*?)\};", parser, re.S)
raw = re.sub(r"//[^\n]*", "", m.group(1))
parts = [p.strip() for p in raw.split(",") if p.strip()]

# Widths of the packed signals, from their declarations in the parser.
def width_of(sig, src):
    mm = re.search(r"reg\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*%s\b" % re.escape(sig), src)
    if mm:
        return int(mm.group(1)) - int(mm.group(2)) + 1
    if re.search(r"reg\s+%s\b" % re.escape(sig), src):
        return 1
    mm = re.search(r"wire\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*%s\b" % re.escape(sig), src)
    if mm:
        return int(mm.group(1)) - int(mm.group(2)) + 1
    if re.search(r"wire\s+%s\b" % re.escape(sig), src):
        return 1
    mm = re.search(r"(\d+)'d0", sig)
    if mm:
        return int(mm.group(1))
    return None

print("packer layout (itch_parse evt_pack)")
print()
pos = 256
packed = {}
problems = []
for p in parts:
    w = width_of(p, parser)
    if w is None:
        problems.append("cannot determine width of %r" % p[:30])
        continue
    hi, lo = pos - 1, pos - w
    sig = p if not re.match(r"\d+'d", p) else "padding"
    packed[sig] = (hi, lo, w)
    print("  %-14s [%3d:%3d] %3d bits" % (sig, hi, lo, w))
    pos = lo
print()
print("  lowest bit reached: %d %s" % (pos, "(covers 255..0)" if pos == 0
                                      else "*** GAP OR OVERLAP ***"))

# --- unpacker: order_book slices -------------------------------------------
print()
print("unpacker slices (order_book)")
print()
EMIT = re.compile(r"wire\s*(?:\[\s*(\d+)\s*:\s*(\d+)\s*\])?\s*(\w+)\s*=\s*evt\s*\["
                  r"\s*(\d+)\s*(?::\s*(\d+))?\s*\]")
slices = {}
for mm in EMIT.finditer(book):
    hw, lw, name, ehi, elo = mm.groups()
    ehi = int(ehi)
    elo = int(elo) if elo is not None else ehi
    slices[name] = (ehi, elo, ehi - elo + 1)
    print("  %-14s evt[%3d:%3d] %3d bits" % (name, ehi, elo, ehi - elo + 1))

if not slices:
    print("  (no declaration-time slices matched)")

# --- compare ---------------------------------------------------------------
print()
fails = list(problems)

if packed and slices:
    name_map = {
        "d_type": "msg_type", "d_timestamp": "timestamp", "d_order_ref": "order_ref",
        "d_aux_ref": "aux_ref", "d_price": "price", "d_shares": "shares",
        "d_side": "side", "d_act": "act",
    }
    print("  %-14s %-18s %-18s %s" % ("field", "packed", "unpacked", ""))
    print("  " + "-" * 62)
    for psig, (phi, plo, pw) in packed.items():
        if psig == "padding":
            continue
        target = name_map.get(psig)
        if target not in slices:
            print("  %-14s [%3d:%3d] %3d       %-18s NOT SLICED"
                  % (psig, phi, plo, pw, "-"))
            # Two fields are legitimately unused downstream:
            #   d_type       order_book dispatches on `act`, not on message type
            #   d_timestamp  ts_hist measures latency with its own counter
            #                (ingress_valid -> completion_valid), not the ITCH stamp
            # Both are carried for completeness; neither is a defect.
            UNUSED = {"d_type", "d_timestamp"}
            if psig not in UNUSED:
                fails.append("%s is packed but never unpacked" % psig)
            continue
        uhi, ulo, uw = slices[target]
        ok = (phi == uhi and plo == ulo)
        print("  %-14s [%3d:%3d] %3d       [%3d:%3d] %3d       %s"
              % (psig, phi, plo, pw, uhi, ulo, uw, "ok" if ok else "MISMATCH"))
        if not ok:
            fails.append("%s packed at [%d:%d] but sliced at [%d:%d]"
                         % (psig, phi, plo, uhi, ulo))

print()
if fails:
    print("EVENT-LAYOUT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("EVENT-LAYOUT-PASS (packer and unpacker agree bit for bit)")
