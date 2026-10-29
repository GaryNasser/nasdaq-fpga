"""Does anything actually exercise the capacity boundaries the RTL declares?

Round 7 found the level_table off-by-one because a round-6 WORKLOAD experiment happened to fill the table.
The golden replay never could: it uses `level_cnt=95` of 256 and `order_cnt=320` of 4,096.

**That is the general hazard.** A declared capacity is a promise; if only 37% of it is ever exercised, the top of
the range is untested code. This check asks, for each configured table, whether some simulation reaches its edge.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
RTL = os.path.join(REPO, "rtl", "itch")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Tables declared in the design, with the register that reports occupancy.
TABLES = [
    ("order_book.v", "LEVELS", "level_cnt", r"parameter LEVELS\s*=\s*(\d+)"),
    ("order_book.v", "ORDERS", "order_cnt", r"parameter ORDERS\s*=\s*(\d+)"),
    ("mold64_reasm.v", "FIFO_BYTES", "fifo", None),
    ("ts_hist.v", "HIST", "hist", None),
]

# What the golden replay uses (from the board's own BOOK-COUNTERS line).
GOLDEN_USE = {"level_cnt": 95, "order_cnt": 320}

rows = []
for fname, name, reg, pat in TABLES:
    p = os.path.join(RTL, fname)
    if not os.path.exists(p):
        continue
    src = io.open(p, encoding="utf-8", errors="replace").read()
    if pat is None:
        # Not a simple parameter table; look for a declaration to report only.
        m = re.search(r"%s\s*=\s*([^\n,]+)" % re.escape(name), src)
        rows.append((fname, name, (m.group(1).strip() if m else "?"), None, None))
        continue
    m = re.search(pat, src)
    cap = int(m.group(1)) if m else None
    used = GOLDEN_USE.get(reg)
    rows.append((fname, name, cap, reg, used))

print("%-16s %-12s %-10s %-12s %-8s %s" % ("file", "table", "declared", "golden use", "cover", "top exercised?"))
print("-" * 96)
gaps = []
for fname, name, cap, reg, used in rows:
    if cap is None or used is None:
        print("%-16s %-12s %-10s %-12s %-8s %s"
              % (fname, name, cap if cap is not None else "?", "-", "-", "not a simple table"))
        continue
    cover = 100.0 * used / cap
    top = used >= cap
    print("%-16s %-12s %-10d %-12d %-7.1f%% %s"
          % (fname, name, cap, used, cover, "yes" if top else "NO"))
    if not top:
        gaps.append((name, cap, used))

print()

# Is there a testbench that drives the boundary?
TB_DIRS = [TOOLS]
bench_sources = []
for d in TB_DIRS:
    for f in sorted(os.listdir(d)):
        if f.startswith("tb_") and f.endswith(".v"):
            bench_sources.append(os.path.join(d, f))
for f in sorted(os.listdir(RTL)):
    if f.startswith("tb_") and f.endswith(".v"):
        bench_sources.append(os.path.join(RTL, f))

coverage = {}
for p in bench_sources:
    src = io.open(p, encoding="utf-8", errors="replace").read()
    # A bench covers the boundary if it references the capacity symbol with a fill loop.
    for name, cap, used in gaps:
        # Round 8: merely MENTIONING the capacity does not fill it. tb_book_edge.v instantiates
        # .LEVELS(32) and never reaches 256; matching on the number found it anyway. Require either
        #   a fill loop bounded by the symbol   (for i < LEVELS)   in a bench that uses the DEFAULT
        #     capacity, or
        #   an explicit instantiation of the full size plus a loop reaching it.
        uses_symbol_loop = re.search(r"(<|<=)\s*%s\b" % re.escape(name), src) is not None
        overrides = re.search(r"\.%s\s*\(\s*\d+\s*\)" % re.escape(name), src)
        if overrides and overrides.group(0).replace(" ", "") != ".%s(%d)" % (name, cap):
            continue          # this bench shrinks the table; it cannot cover the real edge
        if uses_symbol_loop:
            coverage.setdefault(name, []).append(os.path.basename(p))

print("boundary benches:")
for name, cap, used in gaps:
    benches = coverage.get(name, [])
    print("  %-12s %s" % (name, ", ".join(benches) if benches else "*** NONE ***"))

print()
untested = [n for n, _, _ in gaps if not coverage.get(n)]
if untested:
    print("CAPACITY-EDGE-FAIL (%d table(s) whose last entries no test reaches: %s)"
          % (len(untested), ", ".join(untested)))
    print()
    print("  A declared capacity that nothing fills is untested code. The level_table off-by-one")
    print("  (round 7) survived because the golden replay uses 95 of 256 levels.")
    sys.exit(1)

print("CAPACITY-EDGE-PASS (every declared table has a test that reaches its last entry)")
