"""Verify GOLDEN_BOOK in the driver against the recorded baseline file.

The driver now asserts that the hardware book counters equal GOLDEN_BOOK. If that
dict were transcribed wrong, the check would FAIL on a *correct* book - worse
than no check at all, because it would send someone hunting a nonexistent bug.

The values must come from docs/measurements/baseline-a9.txt (the single-stock
subset, stock_locate=6836), and must also agree with the simulation's BOOK-PASS
output. This parses all three and compares.
"""
import io
import sys
import re

BASELINE = r"D:\agent\nasdaq-fpga\docs\measurements\baseline-a9.txt"
DRIVER = r"D:\agent\nasdaq-fpga\board\load_overlay.py"

bl = io.open(BASELINE, encoding="utf-8", errors="replace").read()

# The single-stock section is the first BOOK-COUNTERS line (43428 msgs).
lines = [l for l in bl.splitlines() if "BOOK-COUNTERS:" in l]
if not lines:
    raise SystemExit("no BOOK-COUNTERS line in baseline")
print("baseline BOOK-COUNTERS lines: %d" % len(lines))
first = lines[0]
print("  using: %s" % first.strip()[:110])

# Parse k=v pairs.
baseline = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", first)}

drv = io.open(DRIVER, encoding="utf-8", errors="surrogateescape").read()
m = re.search(r"GOLDEN_BOOK\s*=\s*\{(.*?)\}", drv, re.S)
assert m, "GOLDEN_BOOK not found"
driver = {k: int(v) for k, v in re.findall(r"'(\w+)':\s*(\d+)", m.group(1))}

print()
print("baseline: %s" % baseline)
print("driver  : %s" % driver)
print()

fails = []

# baseline uses short names; map to register names.
alias = {"add": "add_cnt", "exe": "exe_cnt", "can": "can_cnt", "del": "del_cnt",
         "rep": "rep_cnt", "drop": "drop_cnt", "orders": "order_cnt",
         "levels": "level_cnt"}

for bk, reg in alias.items():
    bval = baseline.get(bk)
    dval = driver.get(reg)
    ok = (bval == dval)
    print("  %-10s baseline=%-6s driver=%-6s %s"
          % (bk, bval, dval, "OK" if ok else "MISMATCH"))
    if not ok:
        fails.append("%s: baseline %s vs driver %s" % (reg, bval, dval))

# The simulation's verified output, recorded in the docs.
print()
sim_line = None
for path in (r"D:\agent\nasdaq-fpga\docs\bringup-defects.md",):
    t = io.open(path, encoding="utf-8", errors="replace").read()
    mm = re.search(r"BOOK add=(\d+) exe=(\d+) can=(\d+) del=(\d+) rep=(\d+) drop=(\d+) orders=(\d+) levels=(\d+)", t)
    if mm:
        sim_line = [int(x) for x in mm.groups()]
        break
if sim_line:
    simnames = ["add", "exe", "can", "del", "rep", "drop", "orders", "levels"]
    simv = dict(zip(simnames, sim_line))
    print("simulation (recorded): %s" % simv)
    for bk, reg in alias.items():
        if simv.get(bk) != driver.get(reg):
            fails.append("%s: sim %s vs driver %s" % (reg, simv.get(bk), driver.get(reg)))
    print("simulation agrees with baseline and driver"
          if not fails else "SIMULATION DISAGREES - see FAIL below")
else:
    print("(no recorded simulation BOOK line found; skipped)")

print()
if fails:
    print("GOLDEN-CONST-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    # Exit non-zero: without this the runner records PASS for a check that printed FAIL.
    sys.exit(1)
print("GOLDEN-CONST-PASS")
