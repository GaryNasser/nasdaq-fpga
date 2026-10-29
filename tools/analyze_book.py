"""Quantify the level_table off-by-one before touching the RTL.

`order_book.v` declares `LEVELS = 256` and `LEVEL_ADDR_W = 8` - the address space covers 0..255.

    allocate:   level_table[next_free_level] <= ...      would write index 255
    guard:      if (next_free_level < LEVELS - 1)        stops the pointer at 254
    full test:  if (next_free_level >= LEVELS - 1)       declares full at 255

So indices 0..254 are used (**255 of 256**) and index 255 is never written. `level_cnt=255` in the all-add run is
exactly that limit.

### Why it matters here

`ADDR_DROP_CNT` is documented as "events dropped (order not found / level full)" - **one counter, two causes**. In the
all-add workload, 89,253 of 89,688 orders were dropped (99.5%) and the run took 3,557 ns/message against 296 ns for
the golden replay.

**Before claiming the off-by-one causes that**, check the arithmetic: 256 levels would allow ONE more level - it
cannot explain a 99.5% drop rate on its own. The drop must be dominated by something else.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
OB = os.path.join(REPO, "rtl", "itch", "order_book.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(OB, encoding="utf-8", errors="replace").read()

print("declarations:")
for pat in (r"parameter ORDERS\s*=\s*(\d+)", r"parameter LEVELS\s*=\s*(\d+)",
            r"parameter ORD_ADDR_W\s*=\s*(\d+)", r"parameter LEVEL_ADDR_W\s*=\s*(\d+)"):
    m = re.search(pat, src)
    print("  %-28s %s" % (pat.split("=")[0].replace("parameter", "").strip(),
                          m.group(1) if m else "?"))

levels = int(re.search(r"parameter LEVELS\s*=\s*(\d+)", src).group(1))
addr_w = int(re.search(r"parameter LEVEL_ADDR_W\s*=\s*(\d+)", src).group(1))
orders = int(re.search(r"parameter ORDERS\s*=\s*(\d+)", src).group(1))
ord_w = int(re.search(r"parameter ORD_ADDR_W\s*=\s*(\d+)", src).group(1))

print()
print("address space vs declared size:")
print("  LEVELS %d needs %d address bits for 0..%d; LEVEL_ADDR_W = %d covers 0..%d  %s"
      % (levels, (levels - 1).bit_length(), levels - 1, addr_w, (1 << addr_w) - 1,
         "OK" if (1 << addr_w) >= levels else "TOO SMALL"))
print("  ORDERS %d needs %d bits for 0..%d; ORD_ADDR_W = %d covers 0..%d  %s"
      % (orders, (orders - 1).bit_length(), orders - 1, ord_w, (1 << ord_w) - 1,
         "OK" if (1 << ord_w) >= orders else "TOO SMALL"))

print()
print("the off-by-one:")
guards = re.findall(r"next_free_level\s*(<|>=)\s*LEVELS\s*-\s*1", src)
print("  guards found: %s" % guards)
print("  allocatable indices 0..%d -> %d of %d entries" % (levels - 2, levels - 1, levels))

print()
print("what it can and cannot explain:")
print("  99.5%% of add-orders dropped in the all-add run")
print("  one extra level (256 vs 255) changes the drop count by at most the number of orders")
print("  that map to exactly one more distinct price - it CANNOT explain 89,253 drops")
print("  -> the off-by-one is real but is NOT the cause of that run's drops")
print()
print("  The likely cause is ORDERS: 4,096 entries, and the all-add workload issued 89,688")
print("  add-orders. A direct-mapped order_map of 4,096 cannot hold them; the run's")
print("  order_cnt=9145 is already double the table size.")
