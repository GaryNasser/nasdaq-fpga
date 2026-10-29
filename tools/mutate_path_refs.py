"""Plant a reference to a deleted repository file and confirm detection.

Written in Python after rounds 19, 21 and 23 each showed a PowerShell one-liner
silently failing to apply its edit while still printing success.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

DOC = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_path_refs.py"
MARK = "scripts/deleted_helper.py"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(DOC, backup)

# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=DOC, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

text = io.open(DOC, encoding="utf-8", errors="surrogateescape").read()
text += "\n复现需要运行 `%s`。\n" % MARK
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
