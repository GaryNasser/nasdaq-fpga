"""Fix the probe test: 'return N' must also stop execution, not just record N.

The substitution return N -> RAISED = N records the code but lets the rest of the block
run, so the INPUT-MISSING path fell through into int('') and raised. The test then read
RAISED=None and called it a failure - correct about the harness, wrong about the probe.

Instead of textual substitution, wrap the probe in a function whose body is the extracted
code, so `return` behaves normally. That is both closer to the shipped code and simpler.

Also fixes the probe's own message, which still says "would return 6" after the test
replaced it - no: the message is in the shipped file and reads "would return 6", which is
correct. The "RAISED = 6" seen in the output came from the substitution, not the file.
"""
import io
import os
import re
import sys

RECOVER = r"D:\agent\nasdaq-fpga\tools\board_recover.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(RECOVER, encoding="utf-8").read()

start = src.find("    capture = '/home/xilinx/itch_loc6836.mold64'")
endm = src.find("    print('running the golden comparison", start)
assert start != -1 and endm != -1, "probe block not found"

probe = src[start:endm]
probe = "\n".join(l[4:] if l.startswith("    ") else l for l in probe.split("\n"))

# Build a function around the probe so `return N` works as written.
wrapped = "def probe(sh, BOARD):\n" + "\n".join(
    ("    " + l) if l.strip() else l for l in probe.split("\n")) + "\n    return 0\n"

ns = {}
exec(wrapped, ns)
probe_fn = ns["probe"]


class Out:
    def __init__(self, text):
        self.stdout = text


def make_sh(text):
    def sh(cmd, timeout=None):
        return Out(text)
    return sh


CASES = [
    ("present, right size", "1237116\n", 0),
    ("present, wrong size", "999999\n", 5),
    ("absent (empty)", "", 5),
    ("absent (error text)", "stat: cannot statx\n", 5),
]

print("input probe, exercised with mocked ssh output")
print()
fails = 0
for name, out, want in CASES:
    got = probe_fn(make_sh(out), "mockboard")
    ok = got == want
    if not ok:
        fails += 1
    print("  %-22s mock=%r -> returned %d (want %d) %s"
          % (name, out[:22], got, want, "" if ok else "*** WRONG ***"))

print()
print("  %d of %d cases behaved correctly" % (len(CASES) - fails, len(CASES)))
if fails:
    print("INPUT-PROBE-FAIL")
    sys.exit(1)
print("INPUT-PROBE-PASS")
