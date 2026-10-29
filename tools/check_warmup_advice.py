"""Fail if the documents or driver still recommend a warm-up.

The cold-start defect was a driver reset-ordering bug: CTRL=0x3 set enable and
soft reset in one write, and the transfer started immediately, so the reset pulse
destroyed the word already inside the registered commit stage. The fix is to reset,
wait, then enable.

For several rounds the workaround was a throwaway warm-up packet. That is now gone
and must not come back: a warm-up hides a sequencing error, and any document that
still tells the reader to pre-warm the input is giving advice that would mask a
real defect. The RTL still reports the illegal sequence as broken, via
tools/tb_cold_start.v, so the knowledge is preserved as a test rather than as a
ritual.

Allowed: descriptions that say the warm-up WAS used and WAS removed, and the
--legacy-reset flag whose help text explains it demonstrates the defect.
"""
import io
import os
import re
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = r"D:\agent\nasdaq-fpga"

TARGETS = [
    "docs/final-report.md",
    "docs/status.md",
    "board/load_overlay.py",
    "README.md",
]

# Phrases that instruct or rely on pre-warming.
BAD = re.compile(
    r"(应预热|需要预热|先预热|预热输入|warm[- ]?up packet is needed|"
    r"skip the cold-start warm-up)",
    re.I)

# Contexts that make a mention legitimate.
OK_CONTEXT = re.compile(
    r"(removed|removed in round|WAS|was a workaround|no longer|删除|已删除|"
    r"legacy-reset|demonstrat|临时方案|曾用)",
    re.I)

fails = []
checked = 0
print("scanning for warm-up instructions")

for rel in TARGETS:
    path = os.path.join(REPO, rel)
    if not os.path.exists(path):
        continue
    text = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    for m in BAD.finditer(text):
        checked += 1
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line = text[line_start:line_end if line_end != -1 else len(text)]
        window = text[max(0, m.start() - 300):m.end() + 300]
        if OK_CONTEXT.search(window):
            print("  %s: OK (explained as removed)" % rel)
        else:
            fails.append((rel, line.strip()[:100]))
            print("  %s: STILL RECOMMENDS WARM-UP" % rel)

print()
print("scanned %d file(s), %d mention(s)" % (len(TARGETS), checked))

# The driver must not carry a --no-warmup flag any more: it would be dead, and a
# dead flag implies a workaround still exists.
drv = os.path.join(REPO, "board", "load_overlay.py")
if os.path.exists(drv):
    d = io.open(drv, encoding="utf-8", errors="surrogateescape").read()
    if "--no-warmup" in d:
        fails.append(("board/load_overlay.py", "dead --no-warmup flag"))
        print("  board/load_overlay.py: dead --no-warmup flag")
    if "REG_M64_CTRL, 0x3" in d:
        # only allowed behind --legacy-reset
        i = d.find("REG_M64_CTRL, 0x3")
        window = d[max(0, i - 400):i]
        if "legacy_reset" not in window:
            fails.append(("board/load_overlay.py",
                          "CTRL=0x3 outside the legacy path"))
            print("  board/load_overlay.py: CTRL=0x3 outside legacy path")

print()
if fails:
    print("WARMUP-ADVICE-FAIL (%d)" % len(fails))
    for rel, txt in fails:
        print("  %s: %s" % (rel, txt))
    sys.exit(1)
print("WARMUP-ADVICE-PASS")
