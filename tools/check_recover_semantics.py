"""Fail if the report stops saying what a board_recover run proves.

After round 33 the shipped bitstream and the current one differ, so a successful
recovery run verifies the CURRENT source - not the build the reported figures came
from. That qualification is easy to lose: a later editor tightening the prose sees a
hedge and removes it.

The report must state, in one place:
  * that board_recover.py deploys the current build;
  * the honest claim a pass supports ("the current source passes on hardware");
  * the claim it does NOT support ("the reported numbers were reproduced");
  * why the two builds are functionally comparable (RTL code identical).

Scoped to the section, so an unrelated mention elsewhere cannot satisfy it - the same
mistake round 37's mutation exposed.
"""
import io
import os
import re
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"

if not os.path.exists(REPORT):
    print("RECOVER-SEM-FAIL (no report)")
    sys.exit(1)

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

m = re.search(r"###\s*1\.z[^\n]*", text)
if not m:
    print("  section 1.z absent")
    print()
    print("RECOVER-SEM-FAIL (1)")
    print("  the recovery-semantics section")
    sys.exit(1)

nxt = re.search(r"\n###\s", text[m.end():])
sect = text[m.start():m.end() + nxt.start()] if nxt else text[m.start():]

checks = [
    ("names the deployed bitstream", "0ADD0828" in sect or "当前源码构建" in sect),
    ("states the claim a pass supports", "通过了 golden 比对" in sect),
    ("states the claim it does NOT support", "不是同一句话" in sect),
    ("gives the RTL-identity reason", "代码逐字节一致" in sect),
]

print("recovery semantics (scoped to section 1.z)")
print()
fails = []
for label, ok in checks:
    print("  %-40s %s" % (label, "yes" if ok else "NO"))
    if not ok:
        fails.append(label)

print()
if fails:
    print("RECOVER-SEM-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("RECOVER-SEM-PASS")
