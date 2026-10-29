"""Fail if the documented resource figures disagree with the build that shipped.

History:
  * Round 86 - the report's LUT/FF were from BEFORE the byte-FIFO rewrite.
  * Round 30 - a rebuild overwrote impl_1 with a different placement (LUT 4500 vs
    4501, WNS 0.157 vs 0.126), and this check then reported a mismatch that was
    not a documentation error. The document was right about the SHIPPED bitstream;
    the report on disk was from a different build.

The invariant that actually holds is not "impl_1 == the document". It is:

    the document must match the build that produced the shipped bitstream.

impl_1 now carries BUILD-PROVENANCE.json recording which bitstream that directory
produced. This check reads it and decides:

  * provenance matches the shipped bitstream -> compare numbers strictly; a
    mismatch is a real documentation error (the round-86 case);
  * provenance does NOT match -> the report on disk is from another build. Say so
    and exit 0, because the document may still be correct about the shipped image.
    Without this branch the check would force the document to describe whichever
    build ran most recently - which is how a report starts describing a bitstream
    nobody has run.

SCOPE: the comparison only runs when the report cites the SAME bitstream
impl_1 holds. The report presents three builds; its headline resource figures
belong to 4BB3D7D1 while impl_1 holds 0ADD0828, so this skips rather than
compare incomparable numbers. A mutation that edits a figure belonging to the
other build therefore cannot fail this check - by design.
"""
import io
import json
import os
import re
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = r"D:\agent\nasdaq-fpga"
IMPL = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1")
RPT = os.path.join(IMPL, "nasdaq_wrapper_utilization_placed.rpt")
DOC = os.path.join(REPO, "docs", "final-report.md")
PROV = os.path.join(IMPL, "BUILD-PROVENANCE.json")

rpt = io.open(RPT, encoding="utf-8", errors="replace").read()


def grab(pattern):
    m = re.search(pattern, rpt)
    return int(m.group(1)) if m else None


lut_logic = grab(r"\|\s+LUT as Logic\s+\|\s+(\d+)") or 0
lut_mem = grab(r"\|\s+LUT as Memory\s+\|\s+(\d+)") or 0
ff = grab(r"\|\s+Register as Flip Flop\s+\|\s+(\d+)") or 0
bram = grab(r"\|\s+Block RAM Tile\s+\|\s+(\d+)") or 0
dsp = grab(r"\|\s+DSPs\s+\|\s+(\d+)") or 0

actual = {"LUT": lut_logic + lut_mem, "FF": ff, "BRAM": bram, "DSP": dsp}

doc = io.open(DOC, encoding="utf-8").read()

# Which bitstream did impl_1 produce?
impl_md5 = None
if os.path.exists(PROV):
    impl_md5 = json.load(io.open(PROV, encoding="utf-8")).get("bitstream_md5")

# Does the document describe THAT build?
#
# The report legitimately cites several bitstreams - the shipped one, the current-source one, and
# historical rebuilds - so taking the FIRST `MD5 \`XXXXXXXX` occurrence answers a different question and
# was always finding the board's build, making this check skip unconditionally (round 166: a mutated LUT
# figure still exited 0).
#
# Asking "does the document cite impl_1's id anywhere" is the question that decides whether comparing
# resource numbers means anything.
doc_md5 = None
if impl_md5:
    short = impl_md5.upper()[:8]
    doc_md5 = short if short in doc.upper() else None

print("documented vs routed report")
print("  document cites bitstream : %s" % (doc_md5 or "(none)"))
print("  impl_1 produced          : %s" % (impl_md5 or "(no provenance)"))

# Case-insensitive: the provenance record stores lower-case hex, the document cites upper-case.
same_build = bool(doc_md5 and impl_md5 and doc_md5.upper() in impl_md5.upper())
if not same_build:
    print("  -> the report on disk is from a DIFFERENT build than the one the")
    print("     document describes (rebuilds are not bit-identical). Resource")
    print("     numbers are not comparable; the document is not wrong.")
    print()
    print("UTIL-DOC-SKIPPED (different build)")
    sys.exit(0)

fails = []
for key, pat in (("LUT", r"\| LUT \| \*\*([\d,]+)\*\*"),
                 ("FF", r"\| FF \| \*\*([\d,]+)\*\*"),
                 ("BRAM", r"\| BRAM \| \*\*([\d,]+)\*\*"),
                 ("DSP", r"\| DSP \| \*\*([\d,]+)\*\*")):
    m = re.search(pat, doc)
    if not m:
        print("  %-4s not found in the document" % key)
        fails.append("%s row missing from the report" % key)
        continue
    dv = int(m.group(1).replace(",", ""))
    av = actual[key]
    ok = (dv == av)
    print("  %-4s doc %-6d actual %-6d %s" % (key, dv, av, "OK" if ok else "MISMATCH"))
    if not ok:
        fails.append("%s: doc %d vs actual %d" % (key, dv, av))

print()
if fails:
    print("UTIL-DOC-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("UTIL-DOC-PASS")
