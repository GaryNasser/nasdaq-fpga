"""Require the MD5 to appear inside the provenance section, not anywhere in the file.

The mutation test deleted the MD5 from section 1.y and the check still passed, because
the same MD5 is also cited in section 1.x (added in round 30 to describe the shipped
bitstream). Searching the whole document found that other mention.

The point of the check is that a reader of the provenance section learns which build the
numbers came from. So the search must be scoped to that section's text.
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
    print("HW-PROV-FAIL (no report)")
    sys.exit(1)

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Carve out the provenance section: from its heading to the next same-level heading.
m = re.search(r"###\s*1\.y[^\n]*", text)
if not m:
    print("  provenance section absent")
    print()
    print("HW-PROV-FAIL (1)")
    print("  provenance section present")
    sys.exit(1)

start = m.start()
nxt = re.search(r"\n###\s", text[m.end():])
sect = text[start:m.end() + nxt.start()] if nxt else text[start:]

checks = []
checks.append(("provenance section present", True))
# Scoped: the MD5 must be IN the section.
checks.append(("shipped MD5 inside the section",
               bool(re.search(r"\b4BB3D7D1[0-9A-F]{24}\b", sect))))
checks.append(("measured vs inferred stated", "已测量" in sect and "仅推断" in sect))
checks.append(("next action named", "board_recover.py" in sect))

print("hardware-provenance statements (scoped to section 1.y)")
print()
fails = []
for label, ok in checks:
    print("  %-34s %s" % (label, "yes" if ok else "NO"))
    if not ok:
        fails.append(label)

print()
if fails:
    print("HW-PROV-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("HW-PROV-PASS")
