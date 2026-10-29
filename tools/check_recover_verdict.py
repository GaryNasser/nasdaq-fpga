"""Fail if board_recover.py's verdict returns success on a substring alone.

The golden comparison runs ONCE, after a power cycle that may have been pending for
hours. A false success there is the most expensive error in this project: it would
close the last open hardware question using evidence that says otherwise.

The verdict was a substring test and returned 0 in two of five scenarios:

    B  GOLDEN-OK printed, then a DMA teardown traceback   -> returned 0
    C  GOLDEN-OK printed, ssh truncated at exit 255       -> returned 0

It now requires four conditions, each independently checkable in the source:

    1. the ssh command exited 0                  (clean_exit)
    2. GOLDEN-OK is present                      (saw_golden)
    3. no line starts with FAIL / GOLDEN-FAIL    (saw_fail)
    4. no Python traceback                       (saw_traceback)

and reports which one broke. This check asserts all four are present, so the verdict
cannot quietly regress to `'GOLDEN-OK' in out`.

Also asserted: the old single-expression form is gone.
"""
import io
import os
import re
import sys

PATH = r"D:\agent\nasdaq-fpga\tools\board_recover.py"

if not os.path.exists(PATH):
    print("RECOVER-VERDICT-FAIL (board_recover.py absent)")
    sys.exit(1)

src = io.open(PATH, encoding="utf-8").read()

fails = []
print("board_recover verdict conditions")
print()

CONDITIONS = [
    ("ssh exit code consulted", "clean_exit = (returncode == 0)"),
    ("GOLDEN-OK required", "saw_golden = 'GOLDEN-OK' in out"),
    ("FAIL lines rejected", "saw_fail = any("),
    ("traceback rejected", "saw_traceback = 'Traceback (most recent call last)' in out"),
    ("all four combined",
     "ok = clean_exit and saw_golden and not saw_fail and not saw_traceback"),
]

for label, needle in CONDITIONS:
    ok = needle in src
    print("  %-26s %s" % (label, "present" if ok else "MISSING"))
    if not ok:
        fails.append(label)

# The failure path must say why.
explains = "BOARD-RECOVER-FAIL: %s" in src
print("  %-26s %s" % ("names the broken condition", "yes" if explains else "NO"))
if not explains:
    fails.append("failure reason not reported")

# The old form must be gone.
old = re.search(r"ok\s*=\s*'GOLDEN-OK'\s+in\s+\(", src)
print("  %-26s %s" % ("old substring-only form gone",
                       "yes" if old is None else "STILL PRESENT"))
if old is not None:
    fails.append("old one-line verdict still present")

print()
if fails:
    print("RECOVER-VERDICT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("RECOVER-VERDICT-PASS")
