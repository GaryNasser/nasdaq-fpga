"""Assert that run_sims.py cannot record a pass for a simulation that failed.

The runner used to decide PASS from a single expression:

    got = token in r.stdout

with no check on the exit code and no check that the simulation finished. xsim
reports `Fatal:` yet still exits 0, so a testbench that printed its token and then
tripped a late assertion was recorded as PASS. Demonstrated with tools/tb_trap.v.

The hardened verdict requires four conditions. This check verifies that all four are
present in the source, so the hole cannot silently reopen:

    1. the token appears;
    2. xsim's exit code is 0;
    3. no Fatal:/ERROR: line in the output;
    4. the simulation reached $finish (or a normal-end banner).

It also confirms the failure path reports WHICH condition broke, because a bare
"FAIL" on a four-part test is not debuggable.
"""
import io
import re
import sys

PATH = r"D:\agent\nasdaq-fpga\tools\run_sims.py"
src = io.open(PATH, encoding="utf-8").read()

fails = []
print("simulation verdict conditions")
print()

# Locate the verdict block.
i = src.find("saw_token =")
assert i != -1, "hardened verdict block not found"
block = src[i:i + 1400]

CONDITIONS = [
    ("token appears", "token in r.stdout"),
    ("exit code checked", "returncode == 0"),
    ("no Fatal/ERROR", r"(Fatal|ERROR)"),
    ("reached $finish", "$finish called"),
    ("combined verdict", "got = saw_token and clean_exit and not fatal and finished"),
]

for label, needle in CONDITIONS:
    present = needle in block
    print("  %-20s %s" % (label, "present" if present else "MISSING"))
    if not present:
        fails.append(label)

# The failure path must say which condition broke.
explains = "reasons.append" in block and '" , ".join(reasons)'.replace('" , "', '", "') in block
print("  %-20s %s" % ("explains failure", "yes" if explains else "NO"))
if not explains:
    fails.append("failure reason not reported")

# And the old single-condition form must be gone.
old = re.search(r"got\s*=\s*token in r\.stdout\s*$", src, re.M)
print("  %-20s %s" % ("old form removed", "yes" if old is None else "STILL PRESENT"))
if old is not None:
    fails.append("old one-line verdict still present")

print()
if fails:
    print("SIM-VERDICT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("SIM-VERDICT-PASS")
