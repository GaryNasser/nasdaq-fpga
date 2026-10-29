"""The three replay variants and their expected board deficits, as a record.

This cannot be a live check: it needs the board, and the suite runs offline. What it can be is a
data file the report cites and a future round can re-run:

    variant              first packet A    baseline add    board add    deficit
    _firstA7.mold64              7              14253        14246          7
    _firstA18.mold64            18               5788         5770         18
    _firstA27.mold64            27               9242         9215         27

The check that CAN run offline: the captures exist, the baselines reproduce their counts, and the
deficits still equal the first packets' Add counts when computed from the stored numbers. If a
capture is regenerated or the baseline changes, the stored deficit stops matching and this fails.
"""
import io
import os
import re
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
SRC = os.path.join(REPO, "sw", "baseline", "itch_book_baseline.c")
DATA = os.path.join(REPO, "data")
WORK = os.path.join(os.environ.get("TEMP", "."), "nasdaq_varchk")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Board measurements from round 134, recorded here so a later run can be compared.
MEASURED = [
    ("_firstA7.mold64",   7, 14246),
    ("_firstA18.mold64", 18,  5770),
    ("_firstA27.mold64", 27,  9215),
]

os.makedirs(WORK, exist_ok=True)
exe = os.path.join(WORK, "baseline.exe")
b = subprocess.run(["gcc", "-O2", "-o", exe, SRC], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
if b.returncode != 0:
    print("VARIANT-DATA-FAIL (baseline build failed)")
    sys.exit(1)

print("replay variants: first-packet Add count vs the recorded board deficit")
print()
fails = []
for name, first_a, board_add in MEASURED:
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        print("  %-18s capture missing" % name)
        fails.append("%s missing" % name)
        continue
    r = subprocess.run([exe, "--input", path], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r"add=(\d+)", r.stdout or "")
    if not m:
        fails.append("%s: baseline printed no counters" % name)
        continue
    base = int(m.group(1))
    deficit = base - board_add
    ok = (deficit == first_a)
    print("  %-18s first_A=%-3d base_add=%-6d board_add=%-6d deficit=%-3d  %s"
          % (name, first_a, base, board_add, deficit, "MATCH" if ok else "MISMATCH"))
    if not ok:
        fails.append("%s: deficit %d != first packet's Add count %d"
                     % (name, deficit, first_a))

print()
if fails:
    print("VARIANT-DATA-FAIL (%d)" % len(fails))
    for f in fails:
        print("  %s" % f)
    sys.exit(1)
print("VARIANT-DATA-PASS (all three deficits equal their first packets' Add counts)")
