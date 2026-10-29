"""Confirm the repro-data check catches the missing pack step.

Mutation: remove the `--output data/itch_loc6836.mold64` line, reproducing round 68's
original defect. The check must then report itch_loc6836.mold64 as consumed-but-not-produced.

A second mutation removes the whole section to confirm the "no outputs parsed" guard fires
rather than the check passing on an empty comparison.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_repro_data.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=REPORT, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

MUTATIONS = []

# 1. Drop the itch_loc6836.mold64 packing command.
m1 = re.sub(r"python scripts/pack_itch\.py --input data/itch_loc6836\.raw \\\n"
            r"\s*--output data/itch_loc6836\.mold64 --session NASDAQ01\n", "",
            original, count=1)
if m1 != original:
    MUTATIONS.append(("drop the loc6836 pack step", m1))

# 2. Rename the section so it cannot be found.
m2 = original.replace("### 9.2 数据", "### 9.2 removed", 1)
if m2 != original:
    MUTATIONS.append(("hide section 9.2", m2))

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
if results and all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("REPRO-DATA-MUTATION-PASS")
else:
    print("REPRO-DATA-MUTATION-FAIL")
    sys.exit(1)
