"""Mutations for the image-guard check.

  1. restore the `if not os.path.exists(src_img):` guard  -> stale reuse returns
  2. remove the sys.exit(1) after a failed build          -> failures become non-fatal
  3. change the verdict token so it is unrecognisable     -> the suite would not register it
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

P = r"D:\agent\nasdaq-fpga\tools\run_sims.py"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_image_guard.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(P, backup)
original = io.open(P, encoding="utf-8").read()

MUTATIONS = []

# 1. Reintroduce the exists() guard around build_image.
m1 = original.replace(
    "ok, out = build_image()\nprint(\"generating img.hex ... %s\" % (\"OK\" if ok else \"FAILED\"))",
    "if not os.path.exists(src_img):\n    ok, out = build_image()\n    print(\"generating img.hex ... %s\" % (\"OK\" if ok else \"FAILED\"))",
    1)
if m1 != original:
    MUTATIONS.append(("stale-reuse guard restored", m1))

# 2. Remove the fatal exit.
m2 = original.replace('print("SIMSUITE-FAIL (no test image)")\n    sys.exit(1)',
                      'print("SIMSUITE-FAIL (no test image)")', 1)
if m2 == original:
    m2 = re.sub(r'(\s*)print\("SIMSUITE-FAIL \(no test image\)"\)\s*\n\s*sys\.exit\(1\)',
                '\n    print("SIMSUITE-FAIL (no test image)")', original, count=1)
if m2 != original:
    MUTATIONS.append(("fatal exit removed", m2))

# 3. Rename the verdict token.
m3 = original.replace("SIMSUITE-FAIL (no test image)", "NO IMAGE", 1)
if m3 != original:
    MUTATIONS.append(("token renamed", m3))

if not MUTATIONS:
    print("could not build mutations")
    sys.exit(2)

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(P, "w", encoding="utf-8", newline="\n").write(mutated)
    try:
        compile(mutated, P, "exec")
    except SyntaxError:
        print("%-28s landed but SYNTAX BROKEN - skipped" % name)
        io.open(P, "w", encoding="utf-8", newline="\n").write(original)
        continue
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-28s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(P, "w", encoding="utf-8", newline="\n").write(original)

restored = io.open(P, encoding="utf-8").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, P)
os.unlink(backup)

print()
if results and all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("IMAGE-GUARD-MUTATION-PASS")
else:
    print("IMAGE-GUARD-MUTATION-FAIL")
    sys.exit(1)
