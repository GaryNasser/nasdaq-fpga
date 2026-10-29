import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
from board_recover import verdict as real_verdict
"""Demonstrate that board_recover.py's verdict can be fooled.

The scenario a real run could hit: the remote driver prints GOLDEN-OK, and then the
process dies - a DMA descriptor error during teardown, an XRT exception closing the
overlay, or the ssh session being cut. The output contains GOLDEN-OK, so the current
verdict returns 0.

This simulates the verdict logic in isolation (no board needed) by feeding it the kinds
of stdout the remote command can produce:

  A. clean run                      GOLDEN-OK present, exit 0      -> 0  (correct)
  B. GOLDEN-OK then a crash         GOLDEN-OK present, exit 1      -> 0  (WRONG)
  C. GOLDEN-OK then truncated       GOLDEN-OK present, no finish   -> 0  (WRONG)
  D. no golden result               no GOLDEN-OK, exit 0           -> 1  (correct)
  E. ssh itself failed              empty stdout, exit 255         -> 1  (accidentally right)

Case B is the one that matters: it declares the design verified after it fell over.
"""
import io

# The current verdict, reproduced exactly.
def current_verdict(stdout, rc):
    ok, _why = real_verdict(stdout, rc)
    return 0 if ok else 1


SCENARIOS = [
    ("A clean run",
     "BOOK-CENSUS: ...\nGOLDEN-OK: all 8 book counters match the A9 baseline\n"
     "TS-STATS ...\n",
     0, 0),
    ("B GOLDEN-OK then crash",
     "BOOK-CENSUS: ...\nGOLDEN-OK: all 8 book counters match the A9 baseline\n"
     "Traceback (most recent call last):\n"
     "  File \"load_overlay.py\", line 700, in main\n"
     "RuntimeError: DMA transfer failed at offset 1048576\n",
     1, 1),
    ("C GOLDEN-OK then truncated",
     "GOLDEN-OK: all 8 book counters match the A9 baseline\n",
     255, 1),
    ("D no golden result",
     "FAIL-ASSERT: mold64 RX_PACKETS 849 != 850\n",
     4, 1),
    ("E ssh failure",
     "",
     255, 1),
]

print("board_recover verdict: shipped code vs independently stated expectations")
print()
print("%-28s %-5s %-9s %s" % ("scenario", "rc", "verdict", "expected"))
print("-" * 62)

wrong = 0
for name, stdout, rc, expect in SCENARIOS:
    got_ok, _why = real_verdict(stdout, rc)
    got = 0 if got_ok else 1
    should = expect          # stated per scenario, independently of the code under test
    flag = "" if got == should else "   <-- WRONG"
    if got != should:
        wrong += 1
    print("%-28s %-5d %-9d %-8d%s" % (name, rc, got, should, flag))

print()
print("%d of %d scenarios judged wrongly by the shipped verdict" % (wrong, len(SCENARIOS)))
if wrong:
    print()
    print("  A false success is most costly here: the power cycle, the deploy and the")
    print("  golden comparison happen once per session.")
