"""How many mutation proofs can report MISSED for a mutation that never landed?

Round 28 found `mutate_summary_prov`'s "move markers away" searching for builds that no longer exist: it changed
nothing and blamed the check. The same shape exists wherever a proof replaces text and never confirms the
replacement happened.

**Rewriting 59 scripts in one round is not a change that can be verified.** This check pins the number so it can only
fall: a new proof that replaces text must confirm it landed, and an existing one may be fixed without changing this
check.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
RUNNER = os.path.join(TOOLS, "run_checks.py")
BASELINE = os.path.join(TOOLS, "landing_baseline.txt")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(RUNNER, encoding="utf-8").read()
refs = dict(re.findall(r'"(\w+)":\s*"([\w.]+\.py)"', src))
scripts = sorted(set(refs[n] for n in refs
                     if n.endswith("_proof") or n.startswith("prove_") or n.startswith("mutate_")))

# Round 30: a guard can compare the mutated text against the original in EITHER direction, and
# often reports INCONCLUSIVE rather than printing "landed". Eight of the 21 pinned proofs already had
# such a guard; the pattern only recognised one spelling of it.
LANDED = re.compile(r"\blanded\b|(!=|==)\s*(?:original|orig|body|text|before|base|src)\b|"
                    r"(?:original|orig|body|text|before|base|src)\s*(?:!=|==)|"
                    r"moved\s*!=|changed\s*=|from mutation import|import mutation")
APPENDS = re.compile(r'write\(body \+|write\(text \+|\+ injection|\+ extra')

# A proof needs a landing check only if it REPLACES text and writes the result back. Round 30 found 38 of
# the original 59 never replaced the document at all - they build temp files or add/remove lines, so their
# "mutation" cannot fail to land.
WRITES_BACK = re.compile(r"\.replace\([^)]*\)[^\n]*\n[^\n]*write|"
                         r"mutated\s*=|"
                         r"io\.open\([^)]*\"w\"[^)]*\)[^\n]*write\(\s*(?:mutated|body2|text2)")

unchecked = []
for script in scripts:
    p = os.path.join(TOOLS, script)
    if not os.path.exists(p):
        continue
    s = io.open(p, encoding="utf-8", errors="replace").read()
    if LANDED.search(s):
        continue
    if ".replace(" not in s:
        continue
    if not WRITES_BACK.search(s):
        continue
    unchecked.append(script)

known = set()
if os.path.exists(BASELINE):
    known = set(l.strip() for l in io.open(BASELINE, encoding="utf-8").read().split("\n") if l.strip())
else:
    io.open(BASELINE, "w", encoding="utf-8", newline="\n").write("\n".join(sorted(unchecked)) + "\n")
    known = set(unchecked)
    print("baseline written: %d" % len(known))

new_ones = [s for s in unchecked if s not in known]
fixed = [s for s in known if s not in unchecked]

print("proof scripts                 : %d" % len(scripts))
print("without a landing check       : %d" % len(unchecked))
print("pinned in the baseline        : %d" % len(known))
if fixed:
    print("fixed since the baseline      : %d" % len(fixed))
if new_ones:
    print()
    print("NEW proofs that replace text without confirming it landed:")
    for s in new_ones:
        print("  %s" % s)
    print()
    print("MUTATION-LANDING-FAIL (%d new proof(s) can blame a check for a no-op)" % len(new_ones))
    print("  Use tools/mutation.py: mutate(text, old, new, what) raises when the anchor is absent.")
    sys.exit(1)

print()
print("MUTATION-LANDING-PASS (no new proof can report MISSED for a mutation that never landed;"
      " %d remain pinned)" % len(unchecked))
