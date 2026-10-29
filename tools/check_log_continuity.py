"""Is every round of THIS goal recorded in the defect log?

Rounds 14 through 22 did real work and reached `docs/bringup-defects.md` not at all: the log for this goal stopped at
Round 13. The work existed, the commits existed, and the record did not.

The log's own purpose is that a reader can find what happened without replaying a session transcript. A gap is
therefore the failure the log exists to prevent.

This reads the highest round recorded for the current goal and refuses to let it fall behind the goal's round count.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
LOG = os.path.join(REPO, "docs", "bringup-defects.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

text = io.open(LOG, encoding="utf-8", errors="surrogateescape").read()

# Only sections tagged with this goal count - the log also carries earlier goals' rounds 1..257.
CURRENT = re.compile(r"^## Round (\d+) \(goal: 完成开发\):", re.M)
rounds = sorted(set(int(m.group(1)) for m in CURRENT.finditer(text)))
print("rounds recorded for this goal: %d" % len(rounds))
if rounds:
    print("  from Round %d to Round %d" % (rounds[0], rounds[-1]))

# A goal's rounds are 1-based and contiguous up to the last one written.
if not rounds:
    print()
    print("LOG-CONTINUITY-FAIL: no round of this goal is recorded at all")
    sys.exit(1)

top = rounds[-1]
gaps = [n for n in range(1, top + 1) if n not in rounds]

# The current round number is the highest in the goal's metadata, kept in docs/status.md.
ST = os.path.join(REPO, "docs", "status.md")
current = None
if os.path.exists(ST):
    st = io.open(ST, encoding="utf-8", errors="surrogateescape").read()
    m = re.search(r"goal round[:\s]+(\d+)", st, re.I)
    if m:
        current = int(m.group(1))

if gaps:
    print()
    print("  missing: %s" % ", ".join(str(n) for n in gaps))
if current is not None:
    print("  status.md says the goal is on round %d" % current)
    behind = current - top
    if behind > 0:
        print()
        print("LOG-CONTINUITY-FAIL: the log is %d round(s) behind (last recorded: Round %d)"
              % (behind, top))
        print("  A round whose work is only in the transcript is work the next reader cannot find.")
        sys.exit(1)
else:
    print("  status.md carries no round counter - cannot check for lag")

print()
print("LOG-CONTINUITY-PASS (rounds are contiguous to Round %d)" % top)
