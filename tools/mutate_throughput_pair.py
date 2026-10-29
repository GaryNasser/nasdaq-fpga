"""Confirm check_throughput_pair catches the board figure being buried again.

Mutations:
  1. remove the board figure from the top summary  -> must FAIL
  2. remove the ratio                              -> must FAIL
  3. delete all but one mention of the board figure -> must FAIL
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_throughput_pair.py"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=REPORT, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()


def mutate_head(fn):
    lines = original.split("\n")
    head = fn("\n".join(lines[:60]))
    return head + "\n" + "\n".join(lines[60:])


MUTATIONS = [
    # Round 251: replacing ONE occurrence left five others in place, so the check still found the figure -
    # the mutation proved nothing. To test "the board figure is gone", remove every occurrence.
    ("board figure removed everywhere",
     original.replace("2,230,335", "NNN-NNN")),
    ("ratio removed",
     original.replace("66.7", "XX.X")),
    ("single mention only",
     original.replace("2,230,335", "BOARD-FIG", 2).replace("2,230,335", "X", 1)),
]

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-30s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(original)

restored = io.open(REPORT, encoding="utf-8",
                   errors="surrogateescape").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, REPORT)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("THROUGHPUT-PAIR-MUTATION-PASS")
else:
    print("THROUGHPUT-PAIR-MUTATION-FAIL")
    sys.exit(1)
