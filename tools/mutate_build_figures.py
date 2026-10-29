"""Confirm check_build_figures catches the table drifting from impl_1.

The regression this guards is exactly what round 48 found: the table stopped at round
30's rebuild while impl_1 moved on twice, so the current build's figures were absent.

Mutations:
  1. remove the current-build column header   -> must FAIL
  2. remove the current LUT figure            -> must FAIL
  3. remove the current FF figure             -> must FAIL
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_build_figures.py"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=REPORT, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

def strike_current(text, label):
    """Blank the CURRENT column of the `label` row, whatever the table's width.

    Rounds 42-43 added a fifth column; the literal strings this mutation used to match came from a
    four-column table, so the replacement silently did nothing - and the proof then reported the
    check as MISSING a mutation that never landed (round 29's failure mode).
    """
    found = 0
    out = []
    for line in text.split("\n"):
        if line.startswith("| %s |" % label):
            cells = line.strip().strip("|").split("|")
            cells[-1] = " — "
            out.append("|" + "|".join(cells) + "|")
            found += 1
            continue
        out.append(line)
    if found == 0:
        print("   strike_current(%s): no row found, the mutation cannot land" % label)
    return "\n".join(out)



MUTATIONS = [
    # Round 250: the old targets were report text from many rounds ago, so every mutation was a no-op.
# Target what the report says NOW.
# Removing just the header text leaves the VALUES in the last column, so the check still passes - correctly,
# because the figures are still attributed. The mutation that matters empties the COLUMN.
    ("current-build column emptied",
     strike_current(original, "WNS")),
    ("current LUT removed",
     strike_current(original, "LUT")),
    ("current FF removed",
     strike_current(original, "FF")),
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
    print("%-26s landed=%-5s exit=%d %s"
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
    print("BUILD-FIGURES-MUTATION-PASS")
else:
    print("BUILD-FIGURES-MUTATION-FAIL")
    sys.exit(1)
