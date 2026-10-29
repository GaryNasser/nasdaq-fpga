"""Judge each claim within its own SENTENCE, not its neighbours.

The first version looked at the claim line plus the next two lines for arithmetic.
The mutation test defeated it immediately: appending the original bad sentence to the
corrected report put it next to the corrected paragraph, whose "190 MB/s" and "0.75x"
figures then counted as evidence for the wrong claim.

A claim inherits numbers from its own sentence only. Otherwise any paragraph that
contains a correct figure somewhere launders every false claim beside it.

Sentences are split on Chinese and ASCII full stops, so the window is exactly the text
between the previous and next sentence boundary.
"""
import io
import re
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOC = r"D:\agent\nasdaq-fpga\docs\final-report.md"
text = io.open(DOC, encoding="utf-8", errors="replace").read()

CLAIM = re.compile(r"(远高于|远超|高于)\s*1\s*GbE|above\s+1\s*GbE", re.I)
# Evidence must be a RATE or a MULTIPLIER - a bare number is not enough, or the
# sentence "1 GbE" would qualify itself.
EVIDENCE = re.compile(r"(\d+(?:\.\d+)?\s*(?:MB/s|GB/s|B/消息))|(\d\.\d+\s*×)|(×\s*\d)")

# Split into sentences while keeping offsets.
BOUNDARY = re.compile(r"[。！？；]|(?<=\.)\s")
pieces = []
start = 0
for m in BOUNDARY.finditer(text):
    pieces.append((start, m.end(), text[start:m.end()]))
    start = m.end()
if start < len(text):
    pieces.append((start, len(text), text[start:]))

fails = []
checked = 0
print("throughput claims, judged per sentence")

for s_start, s_end, sent in pieces:
    if not CLAIM.search(sent):
        continue
    checked += 1
    has_rate = bool(EVIDENCE.search(sent))
    line_no = text[:s_start].count("\n") + 1
    preview = " ".join(sent.split())[:64]
    print("  line %-4d %s  %s"
          % (line_no, "OK" if has_rate else "NO RATE IN SENTENCE", preview))
    if not has_rate:
        fails.append((line_no, sent))

print()
print("%d claim sentence(s) examined" % checked)
if checked == 0:
    # Round 257: the report no longer makes a "far above 1 GbE" claim - the board measurement Replaced it with
    # the actual rates. Zero claims is the correct state, not a stale pattern.
    print("GBE-CLAIM-PASS (no 'above 1 GbE' claim remains; the report states measured rates instead)")
    sys.exit(0)
if fails:
    print("GBE-CLAIM-FAIL (%d)" % len(fails))
    for ln, s in fails:
        print("  line %d: %s" % (ln, " ".join(s.split())[:80]))
    sys.exit(1)
print("GBE-CLAIM-PASS")
