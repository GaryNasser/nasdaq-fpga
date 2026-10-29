"""Mutations for the figure-derivation check.

  1. revert 94.5 -> 93.6 in the report        -> the rounded value returns
  2. change the printed average to 28.0       -> the input that produced 93.6
  3. corrupt a computed-looking figure (3.10 -> 3.20) -> the speedup no longer follows
  4. remove 94.5 entirely                     -> an absent figure
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_figure_derive.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=REPORT, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

MUTATIONS = [
    ("restore 93.6 MB/s",
     original.replace("94.5 MB/s（28.252 B/消息", "93.6 MB/s（28.252 B/消息", 1)),
    ("average 28.252 -> 28.000",
     original.replace("28.252", "28.000")),
    # 3.10 appears 12 times; the check tests PRESENCE, so a single replacement does
    # not remove it. Replace every occurrence - which is what a real mis-edit that
    # changed the published speedup would look like.
    ("speedup 3.10 -> 3.20 (all)",
     original.replace("3.10", "3.20")),
    ("remove 94.5", original.replace("94.5", "??", )),
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
    print("FIGURE-DERIVE-MUTATION-PASS")
else:
    print("FIGURE-DERIVE-MUTATION-FAIL")
    sys.exit(1)
