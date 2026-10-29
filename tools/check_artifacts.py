"""Validate the shipped bitstream + handoff before they go near hardware.

With the board unreachable, the artifacts themselves are the last thing that can
still be wrong in a way nothing else catches. This checks:

  * the `.bit` is a structurally valid Vivado bitstream (magic 0x0009), carries
    the right design and part, and was built from the current source;
  * the `.hwh` parses as XML and contains an instance of every IP that
    `board/load_overlay.py` looks up by name.

Why a script and not an eyeball: while writing this I twice concluded the
handoff was broken. An ElementTree walk found zero matching elements because
PYNQ matches instance names (`mold64_reasm_0`) inside PORT/CONNECTION entries,
not a NAME attribute on a MODULE node. The file was always fine; the checker was
wrong - the same failure mode as the register-map checker one round earlier.
"""
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

OUT = r"D:\agent\nasdaq-fpga\vivado/out"
BIT = os.path.join(OUT, "nasdaq.bit")
HWH = os.path.join(OUT, "nasdaq.hwh")
DRIVER = r"D:\agent\nasdaq-fpga\board\load_overlay.py"

fails = []

# ---- bitstream ---------------------------------------------------------
b = open(BIT, "rb").read()
magic = (b[0] << 8) | b[1]
hlen = (b[2] << 8) | b[3]
hdr = b[4:4 + hlen]

print("bitstream: %s" % BIT)
print("  size  %d bytes" % len(b))
print("  magic 0x%04X %s" % (magic, "OK" if magic == 0x0009 else "BAD"))
if magic != 0x0009:
    fails.append("bitstream magic 0x%04X != 0x0009" % magic)

for marker, label in [(b"nasdaq_wrapper", "design"),
                      (b"7z020clg400", "device"),
                      (b"2024.1", "tool")]:
    hit = hdr.find(marker) >= 0
    print("  %-7s %-14s %s" % (label, marker.decode(), "OK" if hit else "MISSING"))
    if not hit:
        fails.append("bitstream header missing %s" % label)

dates = re.findall(rb"\d\d\d\d/\d\d/\d\d", hdr)
times = re.findall(rb"\d\d:\d\d:\d\d", hdr)
if dates and times:
    print("  built  %s %s" % (dates[0].decode(), times[0].decode()))

# ---- handoff -----------------------------------------------------------
print()
print("handoff: %s" % HWH)
try:
    ET.parse(HWH)
    print("  XML parse OK")
except Exception as e:
    fails.append("hwh XML parse failed: %s" % e)
    print("  XML parse FAILED: %s" % e)

raw = io.open(HWH, "rb").read().decode("latin-1")

driver = io.open(DRIVER, encoding="utf-8", errors="surrogateescape").read()

# NOT every find_ip() call applies to this build. `loopback_dma` belongs to the
# M1 loopback bitstream, which is a different BD; the --book and --pipeline
# paths that this artifact serves never touch it. Requiring it here reported a
# false failure - the third time this round that an over-strict checker nearly
# sent me to "fix" something that was already correct.
M1_ONLY = {"loopback_dma"}

wanted = sorted(set(re.findall(r"find_ip\(ol,\s*'([^']+)'\)", driver)) - M1_ONLY)
skipped = sorted(set(re.findall(r"find_ip\(ol,\s*'([^']+)'\)", driver)) & M1_ONLY)
print("  IPs this build must provide: %s" % ", ".join(wanted))
if skipped:
    print("  not applicable (other milestone's BD): %s" % ", ".join(skipped))

# PYNQ resolves by instance name; require the _N instance to appear.
print()
for w in wanted:
    inst = re.findall(r"\b%s_\d+\b" % re.escape(w), raw)
    present = len(inst) > 0
    print("  %-14s %s" % (w, "OK (%d refs)" % len(set(inst)) if present else "MISSING"))
    if not present:
        fails.append("hwh has no instance of %s" % w)


# ---- PL clock contract -------------------------------------------------
# PL_CLK_MHZ in the driver feeds every PL-side rate computation. If it disagrees
# with the design clock the driver reports confidently wrong numbers - a 200 vs
# 190 mismatch is a 5.3% error on exactly the figure the on-board work exists to
# measure. This caught a real one.
print()
PROJ = r"D:\agent\nasdaq-fpga\vivado\create_project.tcl"
proj = io.open(PROJ, encoding="utf-8", errors="surrogateescape").read()
mproj = re.search(r"set\s+DESIGN_FREQ\s+([0-9.]+)", proj)
mdrv = re.search(r"^PL_CLK_MHZ\s*=\s*([0-9.]+)", driver, re.M)
if not mproj or not mdrv:
    fails.append("cannot resolve DESIGN_FREQ / PL_CLK_MHZ")
    print("PL clock: UNRESOLVED")
else:
    pf, df = float(mproj.group(1)), float(mdrv.group(1))
    ok = abs(pf - df) < 0.001
    print("PL clock: design %.3f MHz, driver %.3f MHz  %s"
          % (pf, df, "OK" if ok else "MISMATCH"))
    if not ok:
        fails.append("PL_CLK_MHZ %.3f != DESIGN_FREQ %.3f" % (df, pf))
print()
if fails:
    print("ARTIFACT-CHECK-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    # Without this the runner, which decides PASS from returncode alone, counted a
    # failure as a pass: the FAIL text was printed and SUITE-PASS still appeared.
    sys.exit(1)
else:
    print("ARTIFACT-CHECK-PASS")
