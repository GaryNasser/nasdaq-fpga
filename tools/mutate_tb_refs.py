"""Plant a ghost testbench reference and confirm check_tb_refs catches it.

The first attempt used a PowerShell one-liner whose escaping collapsed, so nothing
was written and the "PASS" it reported tested an unchanged file - the same failure
mode recorded in rounds 19 and 21.

This writes the mutation in Python, verifies it landed by reading the file back, and
only then runs the check.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

DOC = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_tb_refs.py"
MARK = "tb_ghost_test"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(DOC, backup)

# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=DOC, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

text = io.open(DOC, encoding="utf-8", errors="surrogateescape").read()
text += "\n| `%s` | TB-ALL-PASS |\n" % MARK
io.open(DOC, "w", encoding="utf-8", errors="surrogateescape",
        newline="\n").write(text)

landed = MARK in io.open(DOC, encoding="utf-8", errors="surrogateescape").read()
print("mutation landed: %s" % landed)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("check exit code: %d" % r.returncode)
for line in (r.stdout or "").strip().splitlines()[-3:]:
    print("  " + line)

shutil.copyfile(backup, DOC)
os.unlink(backup)

print()
if not landed:
    print("MUTATION-DID-NOT-APPLY")
    sys.exit(2)
if r.returncode == 0:
    print("MUTATION-NOT-CAUGHT")
    sys.exit(1)
print("MUTATION-CAUGHT")
