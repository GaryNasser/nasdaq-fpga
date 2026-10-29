"""consistency classifies a figure as board or simulation by a 400-character window.

    if board and not sim:  return "board"
    if sim and not board:  return "sim"
    return "sim"            # ambiguous -> simulation

L27 is the board summary, but within 400 characters it also mentions the simulation, so the
figure is classified "sim" - and the simulation's expected p50 is ALSO 210.5. Changing the
board figure therefore changes a value the checker compares against the sim table, where it
still matches.

That the board and simulation p50 agree (both 210.5) is a real property of the measurement -
the round-77 note records it - but it makes this check blind to an edit of the board p50 that
lands near a simulation mention.

A mutation that must be caught: change a p99 figure, where board (1136.8) and sim (1178.9)
differ. Editing the board p99 away from its expected value cannot be absorbed by the sim table.

Choosing the label where the two sources disagree is the way to test the classifier at all.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
CHK = os.path.join(TOOLS, "check_internal_consistency.py")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Find the board p99 lines: "1136.8" near 板上.
lines = rep.split("\n")
board_p99 = [(i, l) for i, l in enumerate(lines) if "1136.8" in l and "板上" in l]
print("board p99 occurrences: %d" % len(board_p99))
for i, l in board_p99[:3]:
    print("   L%-5d %s" % (i + 1, l.strip()[:80]))
print()

results = []
if board_p99:
    i, _ = board_p99[0]
    mutated_lines = list(lines)
    mutated_lines[i] = mutated_lines[i].replace("1136.8", "1500.0", 1)
    mutated = "\n".join(mutated_lines)

    bk = tempfile.mktemp(suffix=".md")
    shutil.copyfile(REPORT, bk)
    try:
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
                newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        results.append(("board p99 -> 1500.0", caught))
        for l in out.splitlines():
            if "FAIL" in l or "expected" in l or "disagree" in l:
                print("   %s" % l.strip()[:88])
        print("   exit=%d %s" % (rc, "CAUGHT" if caught else "MISSED"))
        if not caught:
            for l in [x for x in out.splitlines() if x.strip()][-3:]:
                print("      %s" % l[:84])
    finally:
        shutil.copyfile(bk, REPORT)
        os.unlink(bk)
else:
    print("  no board p99 line found")

rc2, _ = run()
print()
print("restored exit=%d" % rc2)

if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("CONSISTENCY-PROOF-FAIL")
sys.exit(1)
