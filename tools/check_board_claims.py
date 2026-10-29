"""Require every board-result claim in the log to state its reproduction count.

Round 1 of this goal reported "850/850 packets, 43428/43428 messages, gap=0" as a
board result. It was a single run of a bitstream that had already been replaced.
Twelve consecutive runs of the bitstream actually on the board gave 849 packets and
err=1463, 12/12 identical.

The root cause is that a board measurement is expensive (40-minute build, deploy,
run), so one sample feels like enough. It is not: the underlying defect varied
between builds, and I attributed a good run to the wrong artifact.

This scans the log for lines that assert a board-level outcome and requires the
surrounding text to state how many times it was reproduced.

Two bugs in the first version, both worth recording because both made it pass
vacuously:

  1. it counted 0 claims - the skip test rejected any line whose 6-line window
     contained the word "simulation", and that window routinely spans a paragraph
     that mentions simulation for unrelated reasons;
  2. because it checked nothing, it printed BOARD-CLAIM-PASS. A check that always
     passes is worse than no check: it reports confidence it never earned.

It now checks the claim LINE for simulation markers only, and fails loudly when it
matches no claims at all - "nothing to check" is not a pass.
"""
import io
import re
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The subject is the REPORT, not the defect log. The log contains history - failed and
# superseded runs - and demanding a run count of every number in it would be wrong.
# This check scanned the log until round 111 and found nothing to object to: the log has
# 17 capture mentions and zero "N/N 包" statements, while the report has 13.
PATH = r"D:\agent\nasdaq-fpga\docs\final-report.md"
text = io.open(PATH, encoding="utf-8", errors="surrogateescape").read()
lines = text.split("\n")

# Match the RESULT SHAPE, not the filename. The report states board outcomes as "N/N 包" and
# "N/N 条"; the capture's filename appears in the reproduction commands instead. Matching the
# filename found commands and skipped results - backwards.
#
# A derivation such as "walk the prefixes -> 43,428 messages" does not use the N/N form, so it is
# not caught by accident.
CLAIM = re.compile(r"\d[\d,]*\s*/\s*\d[\d,]*\s*(?:包|条)")
NUM = re.compile(r"\b\d{2,5}\b")
SIM_MARK = re.compile(r"simulation|SIMSUITE|FULLCHAIN-PASS|REALFILE|tb_", re.I)
# The report is in Chinese; a run count may be written as n=1, 「1 次」, --repeat 1, 各跑, etc.
REPRO = re.compile(
    r"\bruns?\b|reprod|\b12/12\b"
    r"|n\s*=\s*\d+|\d+\s*次|--repeat|重复|各跑|每档|次数", re.I)

fails = []
checked = 0
print("board-result claims and whether they state a reproduction count")
print()

for i, line in enumerate(lines):
    if not CLAIM.search(line):
        continue
    if len(NUM.findall(line)) < 2:
        continue          # a bare filename mention, not a result
    if SIM_MARK.search(line):
        continue          # explicitly a simulation result
    checked += 1
    window = "\n".join(lines[max(0, i - 7):i + 9])
    if REPRO.search(window):
        print("  line %-5d OK - reproduction stated" % (i + 1))
    else:
        fails.append((i + 1, line.strip()[:88]))
        print("  line %-5d NO COUNT: %s" % (i + 1, line.strip()[:78]))

print()
print("checked %d board claim(s)" % checked)

if checked == 0:
    print("BOARD-CLAIM-FAIL: matched no board claims at all")
    print("  a checker that examines nothing must not report a pass")
    sys.exit(1)

if fails:
    print("BOARD-CLAIM-UNREPRODUCED (%d)" % len(fails))
    for ln, txt in fails:
        print("  line %d: %s" % (ln, txt))
    sys.exit(1)
print("BOARD-CLAIM-PASS")
