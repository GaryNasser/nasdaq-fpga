"""Two escapes in the DMA claim check, both real.

1. "assert the claim" was missed. The inserted sentence lived inside a "> " blockquote,
   and the exclusion window (text +/-120 chars) contained the quoted old claim a few lines
   later, so QUOTED matched the window and excused the new assertion.

   The fix: judge each occurrence on ITS OWN line, not on a 240-character neighbourhood.
   A quotation excuses only the characters between its own quote marks.

2. "remove the alternative" was missed because 分块 also appears elsewhere in the report.
   The alternative must be described IN THE CORRECTION BLOCK, not anywhere in the file.

Both are scope faults again - the fifth and sixth - and both are fixed the same way: the
narrowest span that must contain the fact.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TCL = os.path.join(REPO, "vivado", "create_project.tcl")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

for p in (TCL, REPORT):
    if not os.path.exists(p):
        print("DMA-CLAIM-FAIL (missing %s)" % os.path.basename(p))
        sys.exit(1)

tcl = io.open(TCL, encoding="utf-8", errors="replace").read()
text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

s2mm = re.search(r"CONFIG\.c_include_s2mm\s*\{(\d)\}", tcl)
s2mm_on = bool(s2mm and s2mm.group(1) == "1")

CLAIM = re.compile(r"一次(?:--book|测量)?\s*(?:运行|测量)?\s*即(?:可)?关闭")
QUOTE_CHARS = "\"“”「」"
NEGATED = re.compile(r"(?:不成立|并非|不是|不再适用|已更正)")

print("block design facts")
print()
print("  c_include_s2mm : %s" % (s2mm.group(0) if s2mm else "not set"))
print()

fails = []

# Judge each occurrence on its own line.
asserted = []
for m in CLAIM.finditer(text):
    ls = text.rfind("\n", 0, m.start()) + 1
    le = text.find("\n", m.end())
    if le == -1:
        le = len(text)
    line = text[ls:le]
    ln = text[:ls].count("\n") + 1

    # Is the claim inside quotation marks ON THIS LINE?
    before = line[:line.find(m.group(0))] if m.group(0) in line else line[:m.start() - ls]
    if before.count('"') % 2 == 1 or before.count("“") > before.count("”"):
        continue
    # Negated on this line or the next?
    tail = line + "\n" + text[le + 1:text.find("\n", le + 1) if text.find("\n", le + 1) != -1 else len(text)]
    if NEGATED.search(tail):
        continue
    asserted.append(ln)

print("  occurrences of the old claim : %d" % len(CLAIM.findall(text)))
print("  of those, ASSERTED           : %d %s" % (len(asserted), asserted or ""))
print()

if asserted:
    fails.append("the report asserts that one run closes the DMA gap (line %s); the BD "
                 "has S2MM disabled and no bypass" % asserted)

if not s2mm_on:
    disclosed = "c_include_s2mm {0}" in text or "S2MM 未启用" in text
    print("  report discloses S2MM off    : %s" % disclosed)
    if not disclosed:
        fails.append("S2MM is disabled in the BD but the report does not say so")

# The alternative must be described INSIDE the correction block.
start = text.find("第 54 轮更正")
if start == -1:
    fails.append("the S2MM correction block is missing")
    block = ""
else:
    ls = text.rfind("\n\n", 0, start)
    le = text.find("\n\n", start)
    block = text[ls if ls != -1 else start:le if le != -1 else len(text)]

yields = ("分块" in block or "chunk" in block.lower())
print("  alternative described in note: %s" % yields)
if not yields:
    fails.append("the correction block does not say what a board run can produce "
                 "instead of a DMA-only figure")

print()
if fails:
    print("DMA-CLAIM-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("DMA-CLAIM-PASS")
