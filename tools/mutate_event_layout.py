"""The act mutation hit a comment.

`evt[3:0]` first appears inside the file header:

    // Supported actions (from evt[3:0] act field):

so `str.replace(..., 1)` edited the comment and left the RTL alone. `landed` was True
because the file changed; the check correctly reported no mismatch.

Fourth occurrence of this trap in four rounds (62: ST_LEV_CHK, 63: ST_SESSION_CHK, 64:
this). The fix is mechanical and should have been from the start: strip comments before
searching, then apply the edit at the offset found in the stripped text.

Note the narrowness: only `act` failed. `price` and `shares` do not appear in a comment in
that form, so their mutations landed on code. A test suite where three of four mutations
work by luck is worse than one where none do, because it looks like coverage.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

BOOK = r"D:\agent\nasdaq-fpga\rtl\itch\order_book.v"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_event_layout.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".v")
shutil.copyfile(BOOK, backup)
# Round 253: interruption-safe restore. A killed run must not leave a source file modified.
import atexit as _atexit
_atexit.register(lambda _d=BOOK, _b=backup: os.path.exists(_b) and shutil.copyfile(_b, _d))

original = io.open(BOOK, encoding="latin-1").read()


def mask_comments(text):
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


masked = mask_comments(original)

MUTATIONS = [
    ("price +1 bit", "evt[68:37]", "evt[67:36]"),
    ("shares widened", "evt[36:5]", "evt[37:5]"),
    ("act narrowed", "evt[3:0]", "evt[2:0]"),
]

results = []
for name, old, new in MUTATIONS:
    pos = masked.find(old)
    in_comment_only = (pos == -1)
    if pos == -1:
        print("%-20s no CODE occurrence of %r" % (name, old))
        results.append((name, False, False))
        continue
    mutated = original[:pos] + new + original[pos + len(old):]
    landed = mutated != original
    io.open(BOOK, "w", encoding="latin-1", newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-20s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(BOOK, "w", encoding="latin-1", newline="\n").write(original)

restored = io.open(BOOK, encoding="latin-1").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, BOOK)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("EVENT-LAYOUT-MUTATION-PASS")
else:
    print("EVENT-LAYOUT-MUTATION-FAIL")
    sys.exit(1)
