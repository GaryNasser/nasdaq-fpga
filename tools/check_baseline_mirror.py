"""Does the C baseline still mirror the RTL it claims to mirror?

`sw/baseline/itch_book_baseline.c` opens with:

    "This program mirrors the *exact* semantics of the RTL order book (rtl/itch/order_book.v)
     so that the measured throughput is an apples-to-apples comparison"

Round 7 fixed a level_table off-by-one in the RTL. **The C file kept the old form for twelve rounds** - nothing
caught it, because the golden replay uses 95 of 256 levels and never reaches the boundary where they differ.

This checks the specific constructs whose values must agree, rather than trusting the claim.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RTL = os.path.join(REPO, "rtl", "itch", "order_book.v")
C = os.path.join(REPO, "sw", "baseline", "itch_book_baseline.c")

rtl = io.open(RTL, encoding="utf-8", errors="replace").read()
c = io.open(C, encoding="utf-8", errors="replace").read()


def rtl_num(pat, what):
    m = re.search(pat, rtl)
    return int(m.group(1)) if m else None


PARAMS = {
    "ORDERS": rtl_num(r"parameter ORDERS\s*=\s*(\d+)", "ORDERS"),
    "LEVELS": rtl_num(r"parameter LEVELS\s*=\s*(\d+)", "LEVELS"),
}
print("RTL parameters: %s" % PARAMS)

fails = []

# 1  the level allocator's full test
rtl_full = re.search(r"if \(level_cnt >= LEVELS\)", rtl) is not None
c_full = re.search(r"if \(b->level_cnt >= LEVELS\)", c) is not None
c_old = re.search(r"next_free_level >= LEVELS - 1", c) is not None and not c_full
print()
print("  level allocator full test")
print("    RTL  level_cnt >= LEVELS      %s" % ("present" if rtl_full else "MISSING"))
print("    C    level_cnt >= LEVELS      %s" % ("present" if c_full else "MISSING"))
if c_old:
    print("    C    next_free_level >= LEVELS - 1   the PRE-FIX form")
    fails.append("the C baseline still uses the pre-round-7 full test")
if not rtl_full:
    fails.append("the RTL no longer has the round-7 full test - did it revert?")
if not c_full:
    fails.append("the C baseline does not match the RTL full test")

# 2  the linear search must reach the last index
rtl_search = re.search(r"search_idx == LEVELS - 1", rtl) is not None
c_search = re.search(r"for \(i = 0; i < LEVELS; i\+\+\)", c) is not None
c_search_old = re.search(r"for \(i = 0; i < LEVELS - 1; i\+\+\)", c) is not None
print()
print("  linear level search reaches index LEVELS-1")
print("    RTL  searches while search_idx == LEVELS-1   %s" % ("yes" if rtl_search else "NO"))
print("    C    loop bound i < LEVELS                    %s" % ("yes" if c_search else "NO"))
if c_search_old:
    print("    C    loop bound i < LEVELS - 1               the PRE-FIX form")
    fails.append("the C baseline's search stops one index early")
if not c_search:
    fails.append("the C baseline's search does not reach the last index")

# 3  the order map indexing must agree
rtl_ord = rtl_num(r"parameter ORD_ADDR_W\s*=\s*(\d+)", "ORD_ADDR_W")
c_ord = None
m = re.search(r"#define\s+ORD_ADDR_W\s+(\d+)", c)
if m:
    c_ord = int(m.group(1))
print()
print("  order-map index width")
print("    RTL  ORD_ADDR_W = %s" % rtl_ord)
print("    C    ORD_ADDR_W = %s" % (c_ord if c_ord is not None else "(not a #define)"))
if c_ord is not None and rtl_ord is not None and c_ord != rtl_ord:
    fails.append("the C baseline's ORD_ADDR_W (%d) differs from the RTL's (%d)" % (c_ord, rtl_ord))

print()
if fails:
    print("BASELINE-MIRROR-FAIL (%d disagreement(s))" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)

print("BASELINE-MIRROR-PASS (the C baseline's level and order constructs match the RTL)")
