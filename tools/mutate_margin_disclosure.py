"""Mutation test for the setup/hold separation assertions added in round 52.

The error being guarded: the module table comparing setup and hold in one column, and
inventing a setup value for a module whose tight paths are all hold.

Mutations:
  1. merge the two columns back into one "最差" column -> must FAIL
  2. invent a setup value in the order_book row      -> must FAIL
  3. drop the "not comparable" sentence              -> must FAIL
  4. (regression) drop the hold ratio                 -> must FAIL

Mutation 4 used to hardcode "**91 %**", the ratio of the build then on the board. The check
now derives both ratios from the routed timing report, and when the shipped build changed
the mutation stopped landing at all - it rewrote a string the report no longer contained, so
"drop the ratio" mutated nothing and the check passed for the wrong reason. The mutation
derives the number the same way the check does.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_margin_disclosure.py"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=REPORT, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Derive the hold ratio exactly as check_margin_disclosure.py does, so the mutation keeps
# landing after the build - and therefore the ratio - changes.
import re
_VAR = 0.031
_ts = io.open(r"D:\agent\nasdaq-fpga\vivado\workspace\nasdaq\nasdaq.runs\impl_1"
              r"\nasdaq_wrapper_timing_summary_routed.rpt",
              encoding="utf-8", errors="replace").read()
_mt = re.search(r"^\s+(-?\d+\.\d+)\s+-?\d+\.\d+\s+\d+\s+\d+\s+(-?\d+\.\d+)", _ts, re.M)
HOLD_RATIO = int(round(100.0 * _VAR / float(_mt.group(2))))

MUTATIONS = [
    ("merge the columns",
     original.replace("| 模块 | 紧路径数 | 最差建立 | 最差保持 |\n"
                      "| --- | --- | --- | --- |",
                      "| 模块 | 紧路径数 | 最差 |\n| --- | --- | --- |", 1)),
    ("invent order_book setup",
     original.replace("| `order_book` | 4 | — |",
                      "| `order_book` | 4 | +0.036 ns |", 1)),
    ("drop the comparability note",
     original.replace("两列分开，是因为建立与保持的余量**不能互相比较**——它们不是同一把尺子。",
                      "两列分开列出。", 1)),
    ("drop the hold ratio",
     original.replace("**%d %%**" % HOLD_RATIO, "**很高**", 1)),
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
    print("%-28s landed=%-5s exit=%d %s"
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
    print("MARGIN-DISCLOSURE-MUTATION-PASS")
else:
    print("MARGIN-DISCLOSURE-MUTATION-FAIL")
    sys.exit(1)
