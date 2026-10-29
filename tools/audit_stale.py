"""Every checker that reads a log or artifact: does it read the NEWEST one?

Rounds 166-168 and 186 all found the same failure - a checker whose input had gone stale, passing because its
expectation went stale with it. Four instances. That is enough to stop fixing them one at a time and ask which
others share the construction.

### What to find

For each registered checker, extract the paths and globs it reads. Then classify:

    NEWEST-BY-CONSTRUCTION   uses sorted()/max()/getmtime/glob on a rebuild_* or impl_1 pattern
    FIXED PATH               reads one specific file - safe if that file is regenerated, risky if it is a capture
    AMBIGUOUS                could read either

The risky combination is: reads TEMP or a dated capture AND compares against a documented figure. Those are the
ones whose staleness would hide.

### Not a verdict

This produces a list to read. A checker reading a fixed `impl_1` path is correct - that is the current build. A
checker reading a `%TEMP%` capture is the pattern that has failed four times.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

runner = io.open(os.path.join(TOOLS, "run_checks.py"), encoding="utf-8").read()
mapping = dict(re.findall(r'"(\w+)":\s*"([^"]+)"', runner))

TEMP_READERS = []
FIXED_CAPTURE = []
FINE = []

for key, fn in sorted(mapping.items()):
    path = os.path.join(TOOLS, fn)
    if not os.path.exists(path):
        continue
    src = io.open(path, encoding="utf-8", errors="replace").read()
    code = re.sub(r'""".*?"""', "", src, flags=re.S)
    code = re.sub(r"#[^\n]*", "", code)

    reads_temp = bool(re.search(r"environ\.get\(\s*[\"']TEMP", code)) or "%TEMP%" in code
    globs = bool(re.search(r"glob\.glob|os\.listdir", code))
    mtimes = bool(re.search(r"getmtime|st_mtime", code))

    if reads_temp and not (globs and mtimes):
        TEMP_READERS.append((key, fn, "TEMP, no mtime ordering"))
    elif reads_temp:
        FIXED_CAPTURE.append((key, fn, "TEMP with mtime ordering"))
    else:
        FINE.append((key, fn))

print("checkers reading TEMP WITHOUT ordering by mtime: %d" % len(TEMP_READERS))
for k, fn, why in TEMP_READERS:
    print("  %-24s %-34s %s" % (k, fn, why))
print()
print("checkers reading TEMP WITH mtime ordering: %d" % len(FIXED_CAPTURE))
for k, fn, why in FIXED_CAPTURE:
    print("  %-24s %-34s %s" % (k, fn, why))
print()
print("checkers not reading TEMP: %d" % len(FINE))
