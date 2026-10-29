"""Does the bulk-edit guard actually refuse a run-away edit?

Round 13's accident: removing two table rows deleted 1,565 lines. `tools/edit_guard.py` now refuses a rewrite whose
line count moves by more than the edit intends. This proves it refuses - with the exact numbers from that accident.
"""
import io
import os
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
sys.path.insert(0, TOOLS)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import edit_guard

BEFORE = "line %d\n" * 0  # placeholder, replaced below
BEFORE = "".join("line %d\n" % i for i in range(1617))
AFTER_BAD = "".join("line %d\n" % i for i in range(52))
AFTER_OK = "".join("line %d\n" % i for i in range(1615))

cases = [
    ("the round-13 accident (1617 -> 52)", BEFORE, AFTER_BAD, -2, False),
    ("a correct two-line removal (1617 -> 1615)", BEFORE, AFTER_OK, -2, True),
    ("an unguarded export that doubles the file", BEFORE, BEFORE + BEFORE, 0, False),
]

failures = []
for label, a, b, expected, should_pass in cases:
    # Capture the guard's own decision without letting it print over the verdict.
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        ok = edit_guard.assert_size(a, b, expected, label)
    finally:
        sys.stdout = old_stdout
    verdict = "allowed" if ok else "refused"
    want = "allowed" if should_pass else "refused"
    mark = "ok" if ok == should_pass else "WRONG"
    print("  %-46s %-8s (want %-8s) %s" % (label, verdict, want, mark))
    if ok != should_pass:
        failures.append(label)

print()
print("bulk-edit guard cases: %d" % len(cases))

if failures:
    print()
    print("EDIT-GUARD-FAIL (%d case(s) decided wrongly)" % len(failures))
    sys.exit(1)

print()
print("EDIT-GUARD-PASS (a run-away edit is refused; a correct one is allowed)")
