"""fsm_width and windows: two more design checks, both mutable through RTL.

    check_fsm_width   every FSM encoding fits its state register. order_book declares
                      reg [3:0] state and uses encodings up to 14 - room for one more, and
                      the file itself notes "widen to [4:0] before adding a THIRD state".
                      A state at 16 would truncate to 0 and alias ST_IDLE.

    check_windows     every register access stays inside its IP's 4 KB AXI-Lite window. An
                      offset past 0xFFF would address another IP's registers.

Mutations:

    fsm_width   add a state with encoding 4'd16 (truncates to 0) and reference it
    windows     move a register offset past the window

Both are edits to real declarations, verified to land outside comments.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
OB = os.path.join(REPO, "rtl", "itch", "order_book.v")


def strip_comments(t):
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def run(check):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, check)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


cases = []

# --- fsm_width: a state whose encoding does not fit [3:0] -------------------
src = io.open(OB, encoding="latin-1").read()
decl = re.search(r"localparam\s*\[3:0\]\s*ST_MAP_CMP\s*=\s*4'd14\s*;", src)
if decl:
    injected = ("localparam [3:0] ST_OVERFLOW = 4'd16;   // does not fit: truncates to 0\n"
                + decl.group(0))
    mutated = src.replace(decl.group(0), injected, 1)
    cases.append(("fsm_width: 4'd16 in a [3:0] register", OB, mutated,
                  "check_fsm_width.py"))
else:
    print("  fsm_width: ST_MAP_CMP declaration not found")

# --- windows: a register offset past 4 KB ----------------------------------
# Add a decode arm at an offset beyond the window.
anchor = re.search(r"3'd\d+:\s*r_data\s*<=\s*\w+;", src)
if anchor:
    # order_book decodes araddr_r[5:2]; a larger index means a larger byte offset.
    injected = ("          6'd255: r_data <= order_cnt;   // 0x3FC - beyond the 4 KB window\n"
                + anchor.group(0))
    mutated = src.replace(anchor.group(0), injected, 1)
    cases.append(("windows: decode at 0x3FC", OB, mutated, "check_windows.py"))
else:
    print("  windows: a decode arm was not found")

print()
results = []
for name, path, mutated, check in cases:
    before_raw = io.open(path, encoding="latin-1").read()
    if mutated == before_raw:
        print("%-40s NOT APPLIED" % name)
        results.append((name, False, False))
        continue
    if strip_comments(mutated) == strip_comments(before_raw):
        print("%-40s landed only in comments" % name)
        results.append((name, False, False))
        continue
    bk = tempfile.mktemp(suffix=".v")
    shutil.copyfile(path, bk)
    try:
        io.open(path, "w", encoding="latin-1", newline="\n").write(mutated)
        rc, out = run(check)
        caught = rc != 0
        results.append((name, True, caught))
        print("%-40s exit=%d %s" % (name, rc, "CAUGHT" if caught else "MISSED"))
        if not caught:
            for l in [x for x in out.splitlines() if x.strip()][-3:]:
                print("      %s" % l[:88])
    finally:
        shutil.copyfile(bk, path)
        os.unlink(bk)

for check in ("check_fsm_width.py", "check_windows.py"):
    rc, _ = run(check)
    print("%-40s exit=%d (restored)" % (check, rc))

print()
if not results:
    print("RTL-HARNESS2-FAIL (no mutation could be built)")
    sys.exit(1)
if all(l and c for _, l, c in results):
    sys.exit(0)
print("RTL-HARNESS2-FAIL")
sys.exit(1)
