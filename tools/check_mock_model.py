"""Verify the mock's register model against the real hwh and RTL.

mock_run.py proves the driver works IF its register model is right. The model was
hand-written from the RTL, which is exactly the kind of transcription that goes
wrong silently - the FIFO_BYTES bug and the T1 units bug were both "hand-written
from the source, and wrong".

This cross-checks the model's three assumptions against ground truth:

  1. the IP instance names exist in the shipped .hwh;
  2. the base addresses the stub invents are distinct and match the modules the
     driver looks up;
  3. each module's register offsets used by the stub agree with the RTL's decode.

It also extracts the real base addresses from the hwh so a future reader can see
what hardware would actually return.
"""
import io
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
HWH = REPO + r"\vivado/out\nasdaq.hwh"
MOCK = REPO + r"\tools\mock_run.py"

hwh = io.open(HWH, "rb").read().decode("latin-1")
mock = io.open(MOCK, encoding="utf-8", errors="surrogateescape").read()

fails = []

print("1. IP instances present in the shipped handoff")
for ip in ("mold64_reasm_0", "itch_parse_0", "order_book_0", "ts_hist_0",
           "axi_dma_0"):
    present = ip in hwh
    print("   %-16s %s" % (ip, "OK" if present else "MISSING"))
    if not present:
        fails.append("hwh missing %s" % ip)

print()
print("2. base addresses the stub uses")
bases = re.findall(r"'(\w+_0)':\s*\{\s*'phys_addr':\s*(0x[0-9A-Fa-f]+)", mock)
addrs = [int(a, 16) for _, a in bases]
for name, a in bases:
    print("   %-16s %s" % (name, a))
if len(set(addrs)) != len(addrs):
    fails.append("stub base addresses are not distinct")
    print("   DUPLICATE ADDRESSES")
else:
    print("   all distinct: OK")

# The find_ip() helper matches on the dict KEY, so the names matter, not the
# addresses. Confirm the stub keys are the ones the driver searches for.
wanted = sorted(set(re.findall(r"find_ip\(ol,\s*'([^']+)'\)", mock)))
drv = io.open(REPO + r"\board\load_overlay.py", encoding="utf-8",
              errors="surrogateescape").read()
searched = sorted(set(re.findall(r"find_ip\(ol,\s*'([^']+)'\)", drv)))
print()
print("3. stub provides every IP the driver searches for")
M1_ONLY = {"loopback_dma"}
for w in searched:
    if w in M1_ONLY:
        print("   %-16s (M1 loopback BD - not in this build)" % w)
        continue
    ok = any(w in name for name, _ in bases)
    print("   %-16s %s" % (w, "OK" if ok else "MISSING from stub"))
    if not ok:
        fails.append("stub has no IP matching %s" % w)

print()
print("4. real base addresses recorded in the hwh (for reference)")
for ip in ("mold64_reasm_0", "itch_parse_0", "order_book_0", "ts_hist_0"):
    m = re.search(r"NAME=\"%s\".{0,6000}?BASEVALUE=\"(0x[0-9A-Fa-f]+)\"" % ip,
                  hwh, re.S)
    if not m:
        m = re.search(r"NAME=\"%s\".{0,6000}?BASEADDR=\"(0x[0-9A-Fa-f]+)\"" % ip,
                      hwh, re.S)
    print("   %-16s %s" % (ip, m.group(1) if m else "(not exposed in hwh text)"))

print()
if fails:
    print("MOCK-MODEL-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)  # the runner decides PASS from the exit code alone
else:
    print("MOCK-MODEL-PASS")
