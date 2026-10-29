"""A guard for bulk edits to the report: the line count must not move by more than the edit.

Round 13: while removing two table rows from a 1,600-line report, my edit deleted 1,565 lines. The document went
from 1,617 lines to 52, and 80+ checks failed at once.

**The same guard exists for RTL**: `check_bit_repro` compares fingerprints and refuses to call a wildly different
design "a change". Documents had no equivalent.

This is a library, not a check - it is called by the editing scripts, and by `tools/edit_report.py`, so a bulk edit
must declare how many lines it intends to change.
"""
import io
import os
import sys

REPO = r"D:\agent\nasdaq-fpga"


def line_count(text):
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def assert_size(text_before, text_after, expected_delta, what, tol=2):
    """Refuse a rewrite whose line count moved by more than the edit meant to change.

    expected_delta is negative for a deletion. tol allows for trailing-newline differences.
    """
    n0 = line_count(text_before)
    n1 = line_count(text_after)
    delta = n1 - n0
    if abs(delta - expected_delta) > tol:
        print("EDIT-ABORT: %s" % what)
        print("  lines before %d, after %d  (delta %+d, expected %+d)"
              % (n0, n1, delta, expected_delta))
        print("  A bulk edit that removes far more than it meant to is a bug in the edit, not in")
        print("  the document. Nothing was written.")
        return False
    return True


def apply(path, old, new, expected_delta=None, what="replacement"):
    """Read, replace, guard, and only then write. Returns True when the file was changed."""
    text = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    if old not in text:
        print("EDIT-SKIP: %s - anchor not found" % what)
        return False
    expect = expected_delta if expected_delta is not None else (line_count(new) - line_count(old))
    out = text.replace(old, new, 1)
    if not assert_size(text, out, expect, what):
        return False
    st = os.stat(path)
    io.open(path, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(out)
    os.utime(path, (st.st_atime, st.st_mtime))
    print("EDIT-OK: %s (%+d line(s))" % (what, line_count(out) - line_count(text)))
    return True
