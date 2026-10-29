"""Distinguish a comment edit from a design change in the reproducibility check.

`check_bit_repro` compared input timestamps against the baseline bitstream and, when
anything was newer, reported "inputs or resources differ materially: investigate".

Round 35 edited ONLY A COMMENT in create_project.tcl - the CDC explanation. It does not
affect the design at all, but the timestamp moved and the check fired. The same would
happen for a typo fix in an RTL comment.

The distinction that matters: does the input change alter the design? Two cheap tests:

  1. strip comments and blank lines from the changed files and compare against the
     committed versions - if the stripped text is identical, the change is cosmetic;
  2. if any stripped text differs, the change is real and the check should fail.

This is not a proof that the netlist is unchanged (constraints and IP settings also
matter), but it correctly classifies comment-only edits, which is the case that produced
the false alarm.
"""
import io
import os
import re
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"


def strip_comments(text, kind):
    """Remove comments and blank lines, keeping code structure."""
    if kind == "v":
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"//[^\n]*", "", text)
    elif kind == "tcl":
        text = re.sub(r"(?m)^\s*#[^\n]*$", "", text)
        text = re.sub(r"(?m)\s+#[^\n]*$", "", text)
    lines = [l.rstrip() for l in text.split("\n")]
    return "\n".join(l for l in lines if l.strip())


def committed(path):
    """The committed content of a file, or None if untracked."""
    # Explicit UTF-8: the default (GBK on this machine) raised on a byte the
    # Tcl file contains, and the failing subprocess was then read as "new file".
    r = subprocess.run(["git", "show", "HEAD:" + path], cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.stdout if r.returncode == 0 else None


CHANGED = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=REPO,
                         capture_output=True, text=True).stdout.split()

candidates = [f for f in CHANGED
              if f.endswith((".v", ".tcl", ".xdc"))]

print("design-input changes vs the last commit")
print()

real = []
for rel in candidates:
    path = os.path.join(REPO, rel)
    if not os.path.exists(path):
        print("  %-38s DELETED" % rel)
        real.append(rel)
        continue
    old = committed(rel)
    if old is None:
        print("  %-38s new file (counted as real)" % rel)
        real.append(rel)
        continue
    kind = "v" if rel.endswith(".v") else "tcl"
    cur = io.open(path, encoding="utf-8", errors="replace").read()
    old_s = strip_comments(old, kind)
    new_s = strip_comments(cur, kind)
    if old_s == new_s:
        print("  %-38s comment-only edit" % rel)
    else:
        print("  %-38s REAL change (code differs)" % rel)
        real.append(rel)

print()
print("  files with a real design change: %d" % len(real))
for r in real:
    print("     " + r)
