"""Check that the driver's histogram bin width matches the RTL's bucket shift.

The T1 units bug was mechanical and invisible: the RTL assigns a bucket with

    bucket_idx = delta64_r[HIST_BIN_W+2:3]

(a right shift by 3, so 8 cycles per bucket) while the driver assumed 8 ns per
bucket. Both sides said "8", so grepping for a mismatch found nothing - the
factor-of-5.26 error lived entirely in the *interpretation* of the number.

This compares the two definitions directly and also asserts that the driver no
longer contains any constant named as if bins were nanoseconds.
"""
import io
import re
import sys

DRIVER = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
RTL = r"D:\agent\nasdaq-fpga\rtl\itch\ts_hist.v"

drv = io.open(DRIVER, encoding="utf-8", errors="surrogateescape").read()
rtl = io.open(RTL, encoding="utf-8", errors="surrogateescape").read()

fails = []

# ---- RTL bucket shift ----------------------------------------------------
m = re.search(r"bucket_idx\s*=\s*[^;]*?delta64_r\[([^\]]+)\]", rtl, re.S)
if not m:
    print("RTL bucket expression: NOT FOUND")
    fails.append("cannot locate bucket_idx expression")
    rtl_shift = None
else:
    sel = m.group(1)
    print("RTL bucket select: delta64_r[%s]" % sel)
    parts = sel.split(":")
    lo = parts[-1].strip()
    try:
        rtl_shift = int(lo)
    except ValueError:
        rtl_shift = None
    print("  -> bucket spans 2^%s = %s cycles" %
          (lo, (2 ** rtl_shift) if rtl_shift is not None else "?"))

# ---- driver bin width ----------------------------------------------------
m2 = re.search(r"^TS_BIN_CYCLES\s*=\s*(\d+)", drv, re.M)
if not m2:
    print("driver TS_BIN_CYCLES: NOT FOUND")
    fails.append("driver has no TS_BIN_CYCLES")
    drv_bins = None
else:
    drv_bins = int(m2.group(1))
    print("driver TS_BIN_CYCLES = %d" % drv_bins)

print()
if rtl_shift is not None and drv_bins is not None:
    ok = (drv_bins == (2 ** rtl_shift))
    print("bin width: RTL %d cycles, driver %d cycles  %s"
          % (2 ** rtl_shift, drv_bins, "OK" if ok else "MISMATCH"))
    if not ok:
        fails.append("bin width RTL %d != driver %d"
                     % (2 ** rtl_shift, drv_bins))

# ---- the old, wrong name must be gone -----------------------------------
if re.search(r"^TS_BIN_NS\b", drv, re.M):
    fails.append("TS_BIN_NS still present - units are ambiguous again")
    print("TS_BIN_NS: STILL PRESENT")
else:
    print("TS_BIN_NS: absent (units unambiguous)")

# ---- the driver must apply a cycle->ns conversion -----------------------
if "_cycles_to_ns" not in drv:
    fails.append("no _cycles_to_ns conversion in the driver")
    print("cycle->ns conversion: MISSING")
else:
    print("cycle->ns conversion: present")

print()
if fails:
    print("T1UNITS-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("T1UNITS-PASS")
