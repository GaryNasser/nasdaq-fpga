"""Does the check still catch the round-73 fault?

The point of narrowing the classifier (mocks exempt) is to remove false positives without
removing the true positive it was written for. So restore the exact original fault and
require it to be caught:

    chunk_sweep.py:  run_once uses sys.executable and no ssh

Also add a second, synthetic fault: a new script that runs the driver locally with no mock,
to be sure the check generalises beyond one file.

If either passes, the exemption went too far.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
SWEEP = os.path.join(TOOLS, "chunk_sweep.py")
CHECK = os.path.join(TOOLS, "check_board_run_location.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(SWEEP, backup)
original = io.open(SWEEP, encoding="utf-8").read()

# Rebuild the original local invocation.
FAULT = '''def run_once(inp, mb, extra=()):
    """Run the driver's pipeline mode at one chunk size; return (MB/s, output)."""
    cmd = [sys.executable, DRIVER, "--pipeline", "--input", inp,
           "--buffer-mb", str(mb)] + list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    out = (r.stdout or "") + (r.stderr or "")
    m = MBPS.search(out)
    return (float(m.group(1)) if m else None), out'''

i = original.find("def run_once(")
j = original.find("\ndef ", i + 10)
if i == -1:
    print("run_once not found")
    sys.exit(2)
current = original[i:j if j != -1 else len(original)]

mutated = original[:i] + FAULT + "\n" + (original[j:] if j != -1 else "")
landed = mutated != original and "sys.executable, DRIVER" in mutated

results = []

# 1. the real regression
io.open(SWEEP, "w", encoding="utf-8", newline="\n").write(mutated)
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
caught = r.returncode != 0 and "chunk_sweep.py" in ((r.stdout or "") + (r.stderr or ""))
results.append(("restore the round-73 fault", landed, caught))
print("%-30s landed=%-5s exit=%d %s"
      % ("restore the round-73 fault", landed, r.returncode,
         "CAUGHT" if caught else "MISSED"))
io.open(SWEEP, "w", encoding="utf-8", newline="\n").write(original)

# 2. a new script with the same fault and no mock
NEW = os.path.join(TOOLS, "tmp_faulty_runner.py")
io.open(NEW, "w", encoding="utf-8", newline="\n").write(
    'import subprocess, sys, os\n'
    'DRIVER = os.path.join("board", "load_overlay.py")\n'
    'r = subprocess.run([sys.executable, DRIVER, "--pipeline"], capture_output=True)\n'
    'print(r.stdout)\n')
try:
    r2 = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    caught2 = r2.returncode != 0 and "tmp_faulty_runner.py" in ((r2.stdout or "")
                                                               + (r2.stderr or ""))
    results.append(("synthetic faulty runner", True, caught2))
    print("%-30s landed=%-5s exit=%d %s"
          % ("synthetic faulty runner", True, r2.returncode,
             "CAUGHT" if caught2 else "MISSED"))
finally:
    os.remove(NEW)

restored = io.open(SWEEP, encoding="utf-8").read() == original
print("restored: %s" % restored)

r3 = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r3.returncode)

shutil.copyfile(backup, SWEEP)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r3.returncode == 0:
    print("BOARD-RUN-MUTATION-PASS")
else:
    print("BOARD-RUN-MUTATION-FAIL")
    sys.exit(1)
