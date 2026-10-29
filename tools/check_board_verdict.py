import importlib.util
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load the SHIPPED verdict. Copying it here - which an earlier version did - means mutating the
# script cannot reach the check.
spec = importlib.util.spec_from_file_location(
    "board_recover_mod", os.path.join(TOOLS, "board_recover.py"))
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except SystemExit:
    pass
verdict = getattr(mod, "verdict", None)
if verdict is None:
    print("BOARD-VERDICT-FAIL (board_recover.py has no verdict() - the check cannot test it)")
    sys.exit(1)

# The mock's scenarios, plus one it does not contain: GOLDEN-OK, a traceback, and exit 0.
msrc = io.open(os.path.join(TOOLS, "mock_board_recover.py"), encoding="utf-8").read()
mm = re.search(r"SCENARIOS\s*=\s*\[(.*?)\n\]", msrc, re.S)
ns = {}
exec("SCENARIOS = [" + mm.group(1) + "\n]", ns)

EXTRA = [
    ("F GOLDEN-OK, traceback, rc 0",
     "BOOK-CNT: add=15334\nGOLDEN-OK\n"
     'Traceback (most recent call last):\n  File "x.py", line 1\n'
     "RuntimeError: dma teardown\n", 0),
]
scenarios = ns["SCENARIOS"] + EXTRA

EXPECT = {"A": True, "B": False, "C": False, "D": False, "E": False, "F": False}

print("scenario outcomes, decided by board_recover.verdict() itself")
print()
print("  %-30s %-5s %-9s %-9s %s"
      % ("scenario", "rc", "expected", "verdict", "ok"))

fails = []
for item in scenarios:
    if not (isinstance(item, (list, tuple)) and len(item) >= 3):
        continue
    name, stdout, rc = str(item[0]), item[1], item[2]
    key = name.split()[0]
    want = EXPECT.get(key)
    ok, reasons = verdict(stdout, rc)
    agree = (want is None) or (ok == want)
    if not agree:
        fails.append(name)
    print("  %-30s %-5d %-9s %-9s %s"
          % (name[:30], rc, want if want is not None else "-", ok,
             "ok" if agree else "WRONG"))

print()
if fails:
    print("BOARD-VERDICT-FAIL (%d): %s" % (len(fails), ", ".join(fails)))
    print("  a scenario that fell over is being reported as verified")
    sys.exit(1)
print("BOARD-VERDICT-PASS (board_recover.verdict rejects every partial failure)")
