"""Confirm check_utf8 catches a truncated UTF-8 sequence.

The exact fault that was in mold64_reasm.v:
    // CTRL bit0 <EF BF> gates packet acceptance
i.e. the two-byte prefix of U+FFFD inserted where an em dash belonged.

The mutation appends such a sequence to a source file, verifies it landed, runs the
check, then restores the file byte-for-byte.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TARGET = r"D:\agent\nasdaq-fpga\rtl\itch\ts_hist.v"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_utf8.py"

backup = tempfile.mktemp(suffix=".v")
shutil.copyfile(TARGET, backup)

raw = io.open(TARGET, "rb").read()
mutated = raw + b"\n// broken \xef\xbf sequence\n"
io.open(TARGET, "wb").write(mutated)

landed = any(b > 127 for b in io.open(TARGET, "rb").read())
print("mutation landed: %s" % landed)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("check exit code: %d" % r.returncode)
for l in (r.stdout or "").strip().splitlines()[-4:]:
    print("  " + l)

shutil.copyfile(backup, TARGET)
os.unlink(backup)
restored = io.open(TARGET, "rb").read() == raw
print("restored: %s" % restored)

r2 = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r2.returncode)

print()
if landed and r.returncode != 0 and restored and r2.returncode == 0:
    print("UTF8-MUTATION-PASS")
else:
    print("UTF8-MUTATION-FAIL")
    sys.exit(1)
