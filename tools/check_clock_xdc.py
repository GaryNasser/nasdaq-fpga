"""Fail if the SECOND parse of timing_mcyc.xdc is not clean.

timing_mcyc.xdc is loaded twice by design:

    create_project.tcl   before synthesis  -> 105 CRITICAL WARNINGs (nothing elaborated)
    build_overlay.tcl    after synth_1     -> zero warnings, constraints all match

The first parse is expected to be loud. The second parse is the one that actually
constrains impl_1, and it must be silent.

WHY THIS CHECK EXISTS

The build log already contains 105 CRITICAL WARNINGs. If the SECOND parse also started
warning - a renamed clock, a missing hierarchy, a constraint written against an object
that no longer exists - the new warnings would be indistinguishable from the existing
noise. The design would be built with constraints silently not applied, the timing
report would show a passing WNS measured against fewer paths, and nobody would look.

That is the same failure mode as every other entry in this log: a warning that means
"this did not apply" buried among warnings that mean nothing.

The check splits the build log at the second "Parsing XDC File ... timing_mcyc.xdc"
and requires that no WARNING / CRITICAL WARNING / ERROR naming timing_mcyc.xdc appears
after it.
"""
import io
import os
import re
import sys

LOG = r"D:\agent\nasdaq-fpga\build_check\rebuild.log"

if not os.path.exists(LOG):
    print("no build log at %s" % LOG)
    print("CLOCK-XDC-SKIPPED (no log)")
    sys.exit(0)

lines = io.open(LOG, encoding="utf-8", errors="replace").read().split("\n")

parses = [i for i, l in enumerate(lines)
          if "Parsing XDC File" in l and "timing_mcyc.xdc" in l
          and "Finished" not in l]

print("timing_mcyc.xdc parses found: %d" % len(parses))

if len(parses) < 2:
    print("  expected 2 (before and after synthesis)")
    print("CLOCK-XDC-FAIL (the two-stage load is gone; the constraints may not apply)")
    sys.exit(1)

second = parses[-1]
tail = lines[second:]

# Complaints that name the constraint file, after the second parse.
bad = [l for l in tail
       if re.search(r"(WARNING|ERROR)", l) and "timing_mcyc.xdc" in l]

# Also catch the generic form: a constraint warning whose file reference is on the
# same line but written with a different path separator.
if not bad:
    bad = [l for l in tail
           if re.search(r"\[(Vivado 12-508|Vivado 12-627|Vivado 12-4739)\]", l)]

print("  first  parse at line %d (before synthesis)" % (parses[0] + 1))
print("  second parse at line %d (after synth_1)" % (second + 1))
print("  complaints after the second parse: %d" % len(bad))

for l in bad[:6]:
    print("    " + " ".join(l.split())[:110])

print()
if bad:
    print("CLOCK-XDC-FAIL (%d) - the second parse no longer applies cleanly;" % len(bad))
    print("  the design may be built with constraints that did not match, and")
    print("  the 105 expected warnings will hide the new ones.")
    sys.exit(1)
print("CLOCK-XDC-PASS (second parse clean: constraints applied)")
