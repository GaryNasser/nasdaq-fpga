"""Fail if the removed multicycle exception is reintroduced without evidence.

Round 33 measured it unnecessary:

    build without it    WNS +0.042 ns (closes)
    the path's slack    +0.335 ns
    limiting path       pkt_rd_ptr -> pkt_bytes_rem (a different register)

so it was deleted. The history is kept in the file as a comment.

The risk is that someone re-adds it - the old comment claiming a 45 ps miss is still
quoted in the history block, and the next person may read that as a live requirement.
Re-adding it would silently remove a real path from timing analysis.

This check requires:
  * no ACTIVE set_multicycle_path on gap_pending_reg/D;
  * the REMOVED history block still present, so the reasoning travels with the file.

It does NOT forbid multicycle paths in general - a genuine one elsewhere is fine.
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

XDC = r"D:\agent\nasdaq-fpga\vivado\timing_mcyc.xdc"

if not os.path.exists(XDC):
    print("MULTICYCLE-GUARD-SKIPPED (no constraint file)")
    sys.exit(0)

lines = io.open(XDC, encoding="latin-1").read().split("\n")

fails = []
active = []
for i, l in enumerate(lines):
    s = l.strip()
    if s.startswith("#"):
        continue
    if "set_multicycle_path" in s:
        # Collect the continuation lines to see what it applies to.
        block = s
        j = i + 1
        while j < len(lines) and block.rstrip().endswith("\\"):
            block += " " + lines[j].strip()
            j += 1
        if "gap_pending_reg" in block:
            active.append((i + 1, block))

print("multicycle guard on gap_pending_reg/D")
print("  active exceptions on that path: %d" % len(active))
for ln, b in active:
    print("    L%d: %s" % (ln, b[:90]))
    fails.append("active multicycle re-added at L%d" % ln)

history = "REMOVED (round 33)" in "\n".join(lines)
print("  REMOVED history block present : %s" % history)
if not history:
    fails.append("the history block explaining the removal is gone")

print()
if fails:
    print("MULTICYCLE-GUARD-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    print()
    print("  Measured on 2026-10-23: the path has +0.335 ns of slack without the")
    print("  exception, and the build closes at WNS +0.042 ns. Re-adding it is only")
    print("  justified by a NEW measurement showing negative slack.")
    sys.exit(1)
print("MULTICYCLE-GUARD-PASS")
