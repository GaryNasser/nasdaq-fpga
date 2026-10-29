"""Mutate by regex on the assignment, not by an exact-spaced literal.

The constants are aligned with varying whitespace:

    REG_M64_CTRL           = 0x18
    REG_BOOK_CTRL          = 0x30

so a literal with the wrong number of spaces does not match and `landed` is False for all
three. That is the same family of error as the comment and declaration traps: locating a
target by an exact text fragment instead of by the structure that defines it.

The structure here is `NAME<spaces>=<spaces>VALUE`. A regex anchored to the name and
rebuilding the value handles any alignment.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

DRV = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_regmap_map.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, backup)
# Round 253: interruption-safe restore. A killed run must not leave a source file modified.
import atexit as _atexit
_atexit.register(lambda _d=DRV, _b=backup: os.path.exists(_b) and shutil.copyfile(_b, _d))

original = io.open(DRV, encoding="utf-8", errors="surrogateescape").read()

TARGETS = [
    ("REG_BOOK_CTRL", 0x34),
    ("REG_M64_CTRL", 0x20),
    ("REG_IP_CTRL", 0x18),
]

results = []
for name, newval in TARGETS:
    pat = re.compile(r"^(%s)(\s*=\s*)(0x[0-9A-Fa-f]+)" % re.escape(name), re.M)
    m = pat.search(original)
    if not m:
        print("%-22s not found" % name)
        results.append((name, False, False))
        continue
    mutated = original[:m.start(3)] + ("0x%02X" % newval) + original[m.end(3):]
    landed = mutated != original
    io.open(DRV, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-22s %s->0x%02X  exit=%d %s"
          % (name, m.group(3), newval, r.returncode,
             "CAUGHT" if caught else "MISSED"))
    io.open(DRV, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(original)

restored = io.open(DRV, encoding="utf-8",
                   errors="surrogateescape").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, DRV)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("REGMAP-MAP-MUTATION-PASS")
else:
    print("REGMAP-MAP-MUTATION-FAIL")
    sys.exit(1)
