"""Prove check_board_logging fails when a script's writer is removed.

Two mutations:

    1  board_recover.py: delete the record-writing block
    2  chunk_sweep.py:   replace _run_and_save() with a direct call to main()

Both restore the pre-round-105 state, in which the numbers would be console output only. Both
must fail.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
CHK = os.path.join(TOOLS, "check_board_logging.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


CASES = []

# 1. board_recover: remove the persistence block.
p1 = os.path.join(TOOLS, "board_recover.py")
s1 = io.open(p1, encoding="utf-8").read()
start = s1.find("    # Persist the full output.")
end = s1.find("    print()\n    if ok:", start)
if start != -1 and end != -1:
    CASES.append(("board_recover writer removed", p1, s1[:start] + s1[end:]))

# 2. chunk_sweep: call main() directly.
p2 = os.path.join(TOOLS, "chunk_sweep.py")
s2 = io.open(p2, encoding="utf-8").read()
m2 = re.search(r'if __name__ == "__main__":\n    sys\.exit\(_run_and_save\(\)\)', s2)
if m2:
    CASES.append(("chunk_sweep wrapper removed", p2,
                  s2[:m2.start()] + 'if __name__ == "__main__":\n    sys.exit(main())'
                  + s2[m2.end():]))

results = []
for label, path, mutated in CASES:
    orig = io.open(path, encoding="utf-8").read()
    if mutated == orig:
        print("%-32s NOT APPLIED" % label)
        continue
    bk = tempfile.mktemp(suffix=".py")
    shutil.copyfile(path, bk)
    try:
        io.open(path, "w", encoding="utf-8", newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        results.append((label, caught))
        detail = next((l.strip() for l in out.splitlines() if "INCOMPLETE" in l
                       or "BOARD-LOGGING-FAIL" in l), "")
        print("%-32s exit=%d %s  %s" % (label, rc, "CAUGHT" if caught else "MISSED",
                                        detail[:44]))
    finally:
        shutil.copyfile(bk, path)
        os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("BOARD-LOGGING-PROOF-FAIL")
sys.exit(1)
