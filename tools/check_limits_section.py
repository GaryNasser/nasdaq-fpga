"""Replacement mutations that actually exercise the limits check.

Diagnosis of the previous two:

  * "fewer than three items" removed 3 of 14 items, leaving 11 - far above the threshold.
    An invalid mutation: it never put the check in a failing state.

  * "drop the DMA cause" replaced the sentence, but the check searches ITEMS for
    S2MM|旁路, and another item in the same section mentions S2MM in the correction
    blockquote (which is inside the section but not inside an item). So the item-level
    search should have failed... unless the correction blockquote's line also counts as
    part of an item by continuation.

The second is the interesting one: a blockquote following a list item is treated as a
continuation of that item, so the correction text is attributed to whichever item precedes
it. That is a real weakness - a correction block should not lend its wording to a
limitation item.

Rewriting the check to end an item at a blank line or a blockquote, then re-testing.
"""
import io
import os
import re
import sys

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(REPORT):
    print("LIMITS-SECTION-FAIL (no report)")
    sys.exit(1)

lines = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read().split("\n")
FENCE = "`" * 3
inblock = False
start = None
for i, l in enumerate(lines):
    s = l.strip()
    if s.startswith(FENCE):
        inblock = not inblock
        continue
    if not inblock and re.match(r"^#{1,2} .*已知限制", l):
        start = i
        break

if start is None:
    print("LIMITS-SECTION-FAIL (no section titled 已知限制)")
    sys.exit(1)

inblock = False
end = len(lines)
for j in range(start + 1, len(lines)):
    s = lines[j].strip()
    if s.startswith(FENCE):
        inblock = not inblock
        continue
    if not inblock and re.match(r"^#{1,2} ", lines[j]):
        end = j
        break

body_lines = lines[start + 1:end]

# Build items. An item ends at:
#   - the next bulleted/numbered line
#   - a blank line followed by a non-indented, non-continuation line
#   - any blockquote line (corrections are not part of a limitation)
ITEM = re.compile(r"^\s*(?:\d+\.|[*+-])\s+")
items = []
cur = None
for l in body_lines:
    if l.lstrip().startswith(">"):
        if cur is not None:
            items.append("\n".join(cur))
            cur = None
        continue
    if ITEM.match(l):
        if cur is not None:
            items.append("\n".join(cur))
        cur = [l]
    elif cur is not None:
        if l.strip() == "":
            items.append("\n".join(cur))
            cur = None
        elif l.startswith("   ") or l.startswith("\t") or l.startswith("  "):
            cur.append(l)
        else:
            items.append("\n".join(cur))
            cur = None
if cur is not None:
    items.append("\n".join(cur))

print("limitations section, item-scoped and blockquote-excluded")
print()
print("  items: %d" % len(items))
print()

KNOWN = {
    "K1": ("1 GbE", r"(引脚|pin|MIO)"),
    "K2": ("网线到建簿", r"(K1|通路|依赖)"),
    "DMA": ("DMA", r"(S2MM|旁路|bypass)"),
    "全市场": ("全市场", r"(单标的|尺寸|规模|只维护)"),
}

fails = []
for label, (needle, cause) in KNOWN.items():
    holders = [it for it in items if needle in it]
    attributed = [it for it in holders if re.search(cause, it)]
    print("  %-8s items %d, attributed %d" % (label, len(holders), len(attributed)))
    if not holders:
        fails.append("limitation %s does not appear as an item" % label)
    elif not attributed:
        fails.append("limitation %s names the gap without its cause in the same item"
                     % label)
        for it in holders:
            print("       unmatched item: %s" % re.sub(r"\s+", " ", it)[:90])

# A minimum count guards against a gutted section. Four is the measured number.
if len(items) < 4:
    fails.append("only %d items; the section measured 4 before the rewrite" % len(items))

print()
if fails:
    print("LIMITS-SECTION-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("LIMITS-SECTION-PASS")
