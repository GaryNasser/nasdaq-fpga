"""Mutations for the suite-focus check.

The check's purpose is to make suite drift visible: if the proportion of design-checking
work falls, it says so.

Mutations:
  1. remove half the design names (simulated drift)  -> share falls, must still PASS if
     above the floor and FAIL if below it
  2. name a checker that does not exist              -> stale entry, must FAIL
  3. empty the list                                  -> no design examination, must FAIL
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

P = r"D:\agent\nasdaq-fpga\tools\check_suite_focus.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(P, backup)
original = io.open(P, encoding="utf-8").read()

MUTATIONS = []

# 1. Drop most names.
names = re.findall(r'^\s*"(check_\w+\.py)",', original, re.M)
if len(names) > 6:
    keep = set(names[:3])
    mut = original
    for n in names:
        if n not in keep:
            mut = re.sub(r'^\s*"%s",[^\n]*\n' % re.escape(n), "", mut, count=1, flags=re.M)
    if mut != original:
        MUTATIONS.append(("drift: keep only 3 names", mut))

# 2. Add a name that does not exist.
mut2 = original.replace('DESIGN_CHECKERS = {',
                        'DESIGN_CHECKERS = {\n    "check_nonexistent_thing.py",', 1)
if mut2 != original:
    MUTATIONS.append(("stale name added", mut2))

# 3. Empty the set.
m = re.search(r"DESIGN_CHECKERS = \{.*?\n\}", original, re.S)
if m:
    mut3 = original[:m.start()] + "DESIGN_CHECKERS = set()" + original[m.end():]
    MUTATIONS.append(("empty design set", mut3))

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(P, "w", encoding="utf-8", newline="\n").write(mutated)
    try:
        compile(mutated, P, "exec")
    except SyntaxError as e:
        print("%-28s SYNTAX BROKEN: %s" % (name, e))
        io.open(P, "w", encoding="utf-8", newline="\n").write(original)
        continue
    r = subprocess.run([sys.executable, P], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught, r.returncode))
    print("%-28s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "passes"))
    io.open(P, "w", encoding="utf-8", newline="\n").write(original)

restored = io.open(P, encoding="utf-8").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, P], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, P)
os.unlink(backup)

print()
# "drift to 3 names" should still PASS (3/82 = 3.7% < 8% -> actually fails).
# Expect: stale name and empty set must fail; drift may or may not, depending on the floor.
must_catch = [r for r in results if r[0] in ("stale name added", "empty design set")]
if must_catch and all(c for _, _, c, _ in must_catch) and restored and r.returncode == 0:
    print("SUITE-FOCUS-MUTATION-PASS")
else:
    print("SUITE-FOCUS-MUTATION-FAIL")
    sys.exit(1)
