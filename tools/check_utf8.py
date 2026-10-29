"""Fail if a source file contains bytes that are not valid UTF-8.

mold64_reasm.v carried 44 non-ASCII bytes, 22 of them truncated UTF-8 sequences:

    reg enable;  // CTRL bit0 <EF BF?> gates packet acceptance

They came from text written through a converter that saw UTF-8 as latin-1. Synthesis
does not care - they were all inside comments - but every text tool does, and my own
checks raised UnicodeEncodeError on this file three separate times before the cause was
looked at.

An encoding fault in a source file is worth a check because it fails in the dumbest
possible way: not a wrong result, but a crash in whichever tool happens to read the
file next, which then looks like a problem with that tool.

Scope: every .v, .tcl, .xdc and .py under rtl/, vivado/ and tools/. Files whose bytes
decoded as UTF-8 are fine regardless of content.
"""
import glob
import io
import os
import sys

REPO = r"D:\agent\nasdaq-fpga"

PATTERNS = ["rtl/itch/*.v", "vivado/*.tcl", "vivado/*.xdc", "tools/*.py",
            "tools/*.v", "board/*.py", "host/*.c", "sw/**/*.c"]

files = []
for p in PATTERNS:
    files.extend(sorted(glob.glob(os.path.join(REPO, p))))

files = sorted(set(files))

bad = []
print("UTF-8 validity of source files")
print()
for path in files:
    rel = os.path.relpath(path, REPO)
    raw = io.open(path, "rb").read()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        bad.append((rel, e.start, raw[max(0, e.start - 20):e.start + 8]))
        print("  %-40s INVALID at byte %d" % (rel, e.start))

print()
print("%d file(s) checked, %d invalid" % (len(files), len(bad)))
if not files:
    print("UTF8-FAIL (no files matched - the patterns may be stale)")
    sys.exit(1)
if bad:
    print("UTF8-FAIL (%d)" % len(bad))
    for rel, off, ctx in bad:
        print("  %s: offset %d, context %r" % (rel, off, ctx))
    print()
    print("  Repair with tools/repair_mojibake.py after checking that every")
    print("  affected byte is inside a comment.")
    sys.exit(1)
print("UTF8-PASS")
