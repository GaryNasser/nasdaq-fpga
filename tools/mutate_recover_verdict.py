"""Confirm check_recover_verdict catches the verdict regressing to a substring test.

Three mutations:

  1. restore the old one-line form           -> must FAIL
  2. drop the traceback condition            -> must FAIL
  3. drop the exit-code condition            -> must FAIL
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

SF = r"D:\agent\nasdaq-fpga\tools\board_recover.py"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_recover_verdict.py"

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(SF, backup)
original = io.open(SF, encoding="utf-8").read()

MUTATIONS = [
    ("old one-line verdict",
     original.replace(
         "    ok = clean_exit and saw_golden and not saw_fail and not saw_traceback",
         "    ok = 'GOLDEN-OK' in (r.stdout or '')", 1)),
    ("no traceback check",
     original.replace(
         "    saw_traceback = 'Traceback (most recent call last)' in out",
         "    saw_traceback = False", 1)),
    ("no exit-code check",
     original.replace("    clean_exit = (r.returncode == 0)",
                      "    clean_exit = True", 1)),
]

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(SF, "w", encoding="utf-8", newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True)
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-24s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(SF, "w", encoding="utf-8", newline="\n").write(original)

restored = io.open(SF, encoding="utf-8").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True)
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, SF)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("RECOVER-VERDICT-MUTATION-PASS")
else:
    print("RECOVER-VERDICT-MUTATION-FAIL")
    sys.exit(1)
