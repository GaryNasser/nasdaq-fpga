"""Scope the T1 p99 checks to the sentences that state each population.

The first version searched the whole document for "1136.8" and "1,178.9". Replacing the
simulated p99 with the board value (or with "N/A") left the check passing, because
"1136.8" appears elsewhere - in the section 11 table and in the milestone summary - so
the search still found it.

That is the third time this pattern has bitten (rounds 37, 48, now 49): a document-wide
search satisfied by an unrelated mention.

The fix locates the SENTENCE that carries each sample count, and looks for that
population's p99 within it:

    board sentence: contains 19961 and 1136.8
    simulated sentence: contains 19,969 and 1,178.9

If the two values are swapped or made equal, one of the two sentences loses its own p99.
"""
import io
import os
import re
import sys

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(REPORT):
    print("T1-SETS-FAIL (no report)")
    sys.exit(1)

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Split into sentences on Chinese and ASCII terminators, keeping newlines.
BOUNDARY = re.compile(r"[。！？]|(?<=\.)\s")
pieces = []
start = 0
for m in BOUNDARY.finditer(text):
    pieces.append(text[start:m.end()])
    start = m.end()
if start < len(text):
    pieces.append(text[start:])


BOARD_MARK = re.compile(r"板上|AXI DMA|经真实驱动")
SIM_MARK = re.compile(r"仿真|tb_fullchain|SIMSUITE")
MARK = {"board": BOARD_MARK, "sim": SIM_MARK}


def sentence_with(needle, want=None):
    """First sentence carrying `needle` AND the marker of the population asked for.

    Matching on the sample count alone stopped identifying the population when the
    current build's board replay happened to produce 19,969 samples - the same count
    the simulation reports - so the board sentence was read as the simulated one and
    a correct document failed. Requiring the population's own marker is stricter than
    the old code, not looser: a sentence that never says which population it is
    describes cannot satisfy either slot.
    """
    cands = [p for p in pieces if needle in p]
    if want is None:
        return cands[0] if cands else None
    marked = [p for p in cands if MARK[want].search(p)]
    return marked[0] if marked else None


BOARD_N, BOARD_P99 = "19961", "1136.8"
SIM_N, SIM_P99 = "19,969", "1,178.9"

print("T1 figures, checked within the sentence that states each population")
print()

fails = []

for label, count, p99 in (("board", BOARD_N, BOARD_P99),
                          ("simulated", SIM_N, SIM_P99)):
    sent = sentence_with(count, want="board" if label == "board" else "sim")
    if sent is None:
        print("  %-10s sentence with %-8s : NOT FOUND" % (label, count))
        fails.append("no sentence states the %s population (%s samples, with its marker)"
                     % (label, count))
        continue
    has_p99 = p99 in sent
    # The sentence must not also carry the OTHER population's p99 without its count.
    other = SIM_P99 if label == "board" else BOARD_P99
    contaminated = (other in sent) and (
        (SIM_N not in sent) if label == "board" else (BOARD_N not in sent))
    print("  %-10s %-8s -> p99 %-8s: %s%s"
          % (label, count, p99, has_p99,
             "  (also mentions the other p99)" if contaminated else ""))
    if not has_p99:
        fails.append("the %s sentence (%s samples) does not state p99 %s"
                     % (label, count, p99))
    if contaminated:
        fails.append("the %s sentence mixes in the other population's p99" % label)

print()
if fails:
    print("T1-SETS-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("T1-SETS-PASS (each population's p99 sits in its own sentence)")
