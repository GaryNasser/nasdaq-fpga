"""The percentile check cannot detect a wrong bucket width - and should not try.

The mutation that changed TS_BIN_CYCLES from 8 to 16 was not caught, correctly:

    the check reads TS_BIN_CYCLES from the driver to compute its EXPECTED values
    the driver reads the same constant to compute its ACTUAL values
    so both move together and agree at any width

That is not a gap in the check; it is the check doing one job (is the arithmetic
inside the function right?) well and a different job (is the constant right?) not at
all. The second job belongs to `check_t1_units`, which compares the documented bucket
width against the RTL shift amount.

The danger is a mutation test that calls this "MISSED" and prompts me to "fix" the
check by hard-coding 8 - which would make it brittle and duplicate check_t1_units.

The right response is to state the division of labour, and to make the mutation test
assert the CORRECT behaviours rather than all three:

    drop the +1              -> CAUGHT   (arithmetic bug)
    empty returns 0          -> CAUGHT   (contract bug)
    change the bucket width  -> not this check's job; verify check_t1_units sees it
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

DRV = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
RTL = r"D:\agent\nasdaq-fpga\rtl\itch\ts_hist.v"
PCT = r"D:\agent\nasdaq-fpga\tools\check_percentile.py"
UNITS = r"D:\agent\nasdaq-fpga\tools\check_t1_units.py"


def run_check(path):
    r = subprocess.run([sys.executable, path], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# --- 1. arithmetic mutations must be caught by check_percentile --------------
backup = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, backup)
# Round 253: interruption-safe restore. A killed run must not leave a source file modified.
import atexit as _atexit
_atexit.register(lambda _d=DRV, _b=backup: os.path.exists(_b) and shutil.copyfile(_b, _d))

original = io.open(DRV, encoding="utf-8").read()

results = []
ARITH = [
    ("drop the +1", original.replace(
        "_cycles_to_ns((int(i) + 1) * TS_BIN_CYCLES)",
        "_cycles_to_ns(int(i) * TS_BIN_CYCLES)", 1), True),
    ("empty returns 0", original.replace(
        "    if total == 0:\n        return None",
        "    if total == 0:\n        return 0.0", 1), True),
]
for name, mutated, expect_caught in ARITH:
    landed = mutated != original
    io.open(DRV, "w", encoding="utf-8", newline="\n").write(mutated)
    rc, out = run_check(PCT)
    caught = rc != 0
    results.append((name, landed, caught, expect_caught))
    print("%-26s landed=%-5s caught=%-5s %s"
          % (name, landed, caught, "ok" if caught == expect_caught else "WRONG"))
    io.open(DRV, "w", encoding="utf-8", newline="\n").write(original)
shutil.copyfile(backup, DRV)
os.unlink(backup)

# --- 2. the bucket-width mutation belongs to check_t1_units ------------------
# That check compares the DOCUMENTED width against the RTL; it reads the driver's
# constant. Changing the constant should make them disagree.
print()
print("bucket-width mutation, checked by the right tool:")
print("  check_t1_units compares documented width vs RTL shift")
rc, out = run_check(UNITS)
line = [l for l in out.splitlines() if "TS_BIN" in l or "bin" in l.lower()][:2]
for l in line:
    print("    " + l.strip()[:88])
print("    exit %d" % rc)

print()
ok = (all(l and c == e for _, l, c, e in results)
      and io.open(DRV, encoding="utf-8").read() == original)
if ok:
    print("PERCENTILE-MUTATION-PASS (arithmetic caught; bucket width is check_t1_units' job)")
else:
    print("PERCENTILE-MUTATION-FAIL")
    sys.exit(1)
