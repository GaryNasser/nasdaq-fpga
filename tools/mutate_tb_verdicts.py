"""Confirm check_tb_verdicts catches a verdict line with no warning.

Round 23's damage was a table row

    | `tb_mold64_reasm` | TB-ALL-PASS |

with no hint that the testbench hangs. This reintroduces exactly that row and expects
a failure.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

DOC = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_tb_verdicts.py"
MARK = "| `tb_mold64_reasm` | `TB-ALL-PASS` |"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(DOC, backup)

# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=DOC, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

text = io.open(DOC, encoding="utf-8", errors="surrogateescape").read()
# Append a bare verdict far from any existing warning.
text += "\n\n### 附：模块级结果\n\n%s\n" % MARK
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
