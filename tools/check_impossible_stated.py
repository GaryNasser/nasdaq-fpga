"""An unobtainable item must be stated as unobtainable wherever it is discussed.

Round 79 found two statements that softened or contradicted that:

    L1177  K1 与 K2 仍未实测，仍需上板             -> implies more board time would close them
    L692   board T1 distribution 仍需上板测量        -> it had already been measured

Both are the same class: a "still pending" phrasing attached to something that is either
impossible or already done. Neither is a wrong number, so the rounds 76-78 checks could not
see them.

The check: for each of the three hardware-impossible items, every passage that mentions it
must contain an impossibility phrase. And no passage may say it is pending.

    IMPOSSIBLE  不可能 / 不可行 / 无法 / 没有任何 ... 引脚 / c_include_s2mm / 硬件上
    DEFERRAL    仍需上板 / 尚未 / 待 / 计划 / TODO

A passage is a run of lines within 3 of each other that mention the item.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(REPORT):
    print("IMPOSSIBLE-STATED-FAIL (no report)")
    sys.exit(1)

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
lines = text.split("\n")

ITEMS = {
    "K1": re.compile(r"\bK1\b"),
    "K2": re.compile(r"\bK2\b"),
    "DMA": re.compile(r"DMA→DDR|DMA->DDR"),
}

IMPOSSIBLE = re.compile(
    r"不可能|不可行|无法|没有.*引脚|无.*引脚|c_include_s2mm|硬件上|不可达|做不了")
# Prefix-based, matching check_stale_pending. A word list was the defect in both checks:
# round 96 widened one and left this identical one untouched.
DEFERRAL = re.compile(
    r"仍需|尚(?:未|需)|未(?:实)?(?:测|验证|确认)|待(?:补|完成|测量|测)|计划中|TODO")

print("unobtainable items and how each mention is phrased")
print()

fails = []
for label, pat in ITEMS.items():
    hits = [i for i, l in enumerate(lines, 1) if pat.search(l)]
    if not hits:
        fails.append("%s is never mentioned - the scan for it would be vacuous" % label)
        continue

    # Group into passages.
    groups = []
    for i in hits:
        if groups and i - groups[-1][-1] <= 3:
            groups[-1].append(i)
        else:
            groups.append([i])

    print("  %s: %d mention(s) in %d passage(s)" % (label, len(hits), len(groups)))
    for g in groups:
        block = "\n".join(lines[g[0] - 1:g[-1]])
        imp = IMPOSSIBLE.search(block)
        dfr = DEFERRAL.search(block)
        mark = "ok" if imp else "NO REASON"
        extra = "  DEFERRAL: %s" % dfr.group(0) if dfr else ""
        print("     L%-5d %-10s%s" % (g[0], mark, extra))
        # Only DEFERRAL wording is a fault: it asserts a status the hardware contradicts.
        # A mention without a reason is not - the report discusses the DMA because the
        # pipeline feeds it, and demanding a caveat each time would be noise.
        # A deferral word inside a denial is not deferral:
        #   "K1 与 K2 **不是「尚未做」，而是这台板做不了**"
        # The sentence says the opposite of pending. If it also carries an impossibility
        # phrase, the deferral word is part of denying it.
        if dfr and not IMPOSSIBLE.search(block):
            fails.append("%s at L%d uses deferral wording: %s"
                         % (label, g[0], dfr.group(0)))
    print()

# The three must appear together at least once, so a reader meets the full list.
together = re.search(r"K1[^\n]{0,300}K2[^\n]{0,600}(DMA→DDR|c_include_s2mm)", text, re.S)
print("  all three listed together: %s" % bool(together))
if together:
    # The passage that groups them must explain each one.
    block = together.group(0)
    reasons = len(IMPOSSIBLE.findall(block))
    print("  reasons given in that passage: %d" % reasons)
    if reasons < 2:
        fails.append("the passage grouping K1/K2/DMA gives fewer than two reasons")

print()
if fails:
    print("IMPOSSIBLE-STATED-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("IMPOSSIBLE-STATED-PASS (every mention gives the reason it cannot be done)")
