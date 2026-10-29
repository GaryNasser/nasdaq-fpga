"""Verify the driver's plausibility guard fires on corrupt PL timing data.

The guard exists because two silent failure modes produce the same symptom - an
absurd cycle count from TSNOW:

  * a 32-bit wrap if a transfer ever exceeds 22.6 s at 190 MHz;
  * a torn LO/HI pair if read64() runs while a counter is still advancing.

Either would be published as a confident, wrong msg_per_s. This check proves the
guard discriminates: it must stay silent on correct data and fire on corrupt.

It runs the real driver twice against the simulated overlay, once with a sane
TSNOW and once with a corrupted one, and requires WARN-IMPLAUSIBLE only in the
second case.
"""
import io
import os
import re
import shutil
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
WORK = os.path.join(os.environ["TEMP"], "nasdaq_guardcheck")

MOCK = os.path.join(os.environ["TEMP"], "nasdaq_mockrun")

os.makedirs(WORK, exist_ok=True)

# Reuse mock_run.py's harness to lay down the stub + driver + data.
r = subprocess.run([sys.executable, os.path.join(REPO, "tools", "mock_run.py")],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
if "MOCK-RUN-PASS" not in r.stdout:
    print("prerequisite mock_run did not pass")
    print(r.stdout[-1500:])
    sys.exit(1)

for name in ("pynq.py", "numpy.py", "load_overlay.py", "itch_loc6836.mold64",
             "nasdaq.bit", "nasdaq.hwh"):
    src = os.path.join(MOCK, name)
    if os.path.exists(src):
        shutil.copy(src, os.path.join(WORK, name))

pynq_path = os.path.join(WORK, "pynq.py")
original = io.open(pynq_path, encoding="utf-8").read()

SANE_STEP = "m[0x478] = m.get(0x478, 0) + 250000"
CORRUPT_STEP = "m[0x478] = (m.get(0x478, 0) + 0x0B000000) & 0xFFFFFFFF"

if SANE_STEP not in original:
    print("cannot find the TSNOW step in the stub")
    sys.exit(1)

env = dict(os.environ)
env["PYTHONPATH"] = WORK


def run(step):
    patched = original.replace(SANE_STEP, step)
    io.open(pynq_path, "w", encoding="utf-8", newline="\n").write(patched)
    return subprocess.run(
        [sys.executable, "load_overlay.py", "--book",
         "--input", "itch_loc6836.mold64", "--repeat", "1"],
        cwd=WORK, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env).stdout


sane = run(SANE_STEP)
corrupt = run(CORRUPT_STEP)
shutil.copy(os.path.join(MOCK, "pynq.py"), pynq_path)  # restore

print("sane TSNOW    : WARN-IMPLAUSIBLE present = %s"
      % ("WARN-IMPLAUSIBLE" in sane))
print("corrupt TSNOW : WARN-IMPLAUSIBLE present = %s"
      % ("WARN-IMPLAUSIBLE" in corrupt))

fails = []
if "WARN-IMPLAUSIBLE" in sane:
    fails.append("guard fired on correct data (false positive)")
if "WARN-IMPLAUSIBLE" not in corrupt:
    fails.append("guard did NOT fire on corrupt data")
if "GOLDEN-OK" not in sane:
    fails.append("the sane run did not reach GOLDEN-OK")

m = re.search(r"WARN-IMPLAUSIBLE: TSNOW delta (\d+) cycles", corrupt)
if m:
    print("corrupt delta : %s cycles" % m.group(1))

print()
if fails:
    print("GUARD-CHECK-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("GUARD-CHECK-PASS")
