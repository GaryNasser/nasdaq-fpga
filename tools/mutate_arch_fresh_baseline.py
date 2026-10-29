"""Confirm the baseline test fails when the baseline regresses to timestamps.

If someone reverts check_arch_fresh to mtime-only comparison, case A (mtime moved,
content identical) would report stale - and the test must catch that.

Mutation: replace differs_from_build's body with the old mtime rule.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

FRESH = r"D:\agent\nasdaq-fpga\tools\check_arch_fresh.py"
TEST = r"D:\agent\nasdaq-fpga\tools\test_arch_fresh_baseline.py"

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(FRESH, backup)
original = io.open(FRESH, encoding="utf-8").read()

# Replace the content comparison with a pure timestamp rule.
MUT = original.replace(
    """    rel = os.path.relpath(p, REPO).replace(os.sep, "/")
    entry = _rec.get(rel)
    if entry and entry.get("code_md5"):
        return _code_md5(p) != entry["code_md5"]
    # No record: keep the previous behaviour.
    return not unchanged_vs_head(p)""",
    """    return os.path.getmtime(p) > os.path.getmtime(BIT)""", 1)

landed = MUT != original
io.open(FRESH, "w", encoding="utf-8", newline="\n").write(MUT)

r = subprocess.run([sys.executable, TEST], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
caught = r.returncode != 0
print("mutation landed: %s" % landed)
print("test exit code : %d %s" % (r.returncode, "CAUGHT" if caught else "MISSED"))
for line in (r.stdout or "").strip().splitlines()[-5:]:
    print("  " + line)

shutil.copyfile(backup, FRESH)
os.unlink(backup)
restored = io.open(FRESH, encoding="utf-8").read() == original
print("restored: %s" % restored)

r2 = subprocess.run([sys.executable, TEST], capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r2.returncode)

print()
if landed and caught and restored and r2.returncode == 0:
    print("ARCH-FRESH-BASELINE-MUTATION-PASS")
else:
    print("ARCH-FRESH-BASELINE-MUTATION-FAIL")
    sys.exit(1)
