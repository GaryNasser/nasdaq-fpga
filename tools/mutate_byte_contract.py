"""The tvalid mutation hit a declaration, not the assignment.

`out_valid` appears first as `wire out_valid;` or inside a concatenation, so replacing the
first literal occurrence edited something that is not `assign m_axis_tvalid = out_valid;`.
The assignment stayed as it was and the check correctly reported no violation.

Rounds 62-64 each lost one mutation to this family of errors; the lesson is the same and
still not automatic: locate the mutation target by the structure that defines it, not by
the first occurrence of a token.

Here the target is the right-hand side of `assign m_axis_tvalid = ...`, which the check
itself already parses. Reuse that parse to build the mutation.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

PROD = r"D:\agent\nasdaq-fpga\rtl\itch\mold64_reasm.v"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_byte_contract.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".v")
shutil.copyfile(PROD, backup)
# Round 253: interruption-safe restore. A killed run must not leave a source file modified.
import atexit as _atexit
_atexit.register(lambda _d=PROD, _b=backup: os.path.exists(_b) and shutil.copyfile(_b, _d))

original = io.open(PROD, encoding="latin-1").read()

# Find the actual assignment to m_axis_tvalid and replace only its RHS.
m = re.search(r"assign\s+m_axis_tvalid\s*=\s*([^;]+);", original)
if not m:
    print("m_axis_tvalid assignment not found")
    sys.exit(2)

rhs = m.group(1).strip()
print("current: assign m_axis_tvalid = %s;" % rhs)

mutated = original[:m.start(1)] + " 1'b1 " + original[m.end(1):]
landed = mutated != original
io.open(PROD, "w", encoding="latin-1", newline="\n").write(mutated)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
out = (r.stdout or "") + (r.stderr or "")
caught = r.returncode != 0
print("mutated: assign m_axis_tvalid = 1'b1;")
print("landed=%s  exit=%d  %s" % (landed, r.returncode,
                                   "CAUGHT" if caught else "MISSED"))
if caught:
    for line in out.splitlines():
        if "unconditional" in line:
            print("  check says: %s" % line.strip())

io.open(PROD, "w", encoding="latin-1", newline="\n").write(original)
restored = io.open(PROD, encoding="latin-1").read() == original
print("restored: %s" % restored)

r2 = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r2.returncode)

shutil.copyfile(backup, PROD)
os.unlink(backup)

print()
if landed and caught and restored and r2.returncode == 0:
    print("BYTE-CONTRACT-MUTATION-PASS")
else:
    print("BYTE-CONTRACT-MUTATION-FAIL")
    sys.exit(1)
