"""Every session regression in the suite must be mentioned in the report's limitations.

The suite holds three session-related entries that currently FAIL by design:

    session_bad    a bad first session is accepted
    false_sync     the rescan locks onto a payload session id
    pause_sweep    a long pause loses packets

Those are declared KIND_EXPECTED, so the suite is green whether or not anyone writes them down.
Rounds 122-128 spent seven rounds finding them; the report is the artefact that must carry them.

This check ties the two together: for each session-behaviour suite entry, the report must contain
the testbench name. Naming the file forces the sentence that says what it does.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
SIMS = os.path.join(REPO, "tools", "run_sims.py")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sims = io.open(SIMS, encoding="utf-8").read()
rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Suite entries whose testbench exercises session behaviour.
SESSION_TBS = re.findall(r'\("(\w+)",\s*"(tb_(?:session|false_sync|pause)\w*\.v)"', sims)
SESSION_TBS = [(name, tb) for name, tb in SESSION_TBS if not tb.endswith("_probe.v")]

print("session-behaviour testbenches in the suite")
print()
missing = []
for name, tb in SESSION_TBS:
    named = tb in rep
    print("  %-16s %-24s in the report: %s" % (name, tb, named))
    if not named:
        missing.append(tb)

print()
print("  checked %d testbench name(s)" % len(SESSION_TBS))
print()

if not SESSION_TBS:
    print("SESSION-COVERAGE-FAIL (no session testbenches found - the check would be vacuous)")
    sys.exit(1)

if missing:
    print("SESSION-COVERAGE-FAIL (%d)" % len(missing))
    for m in missing:
        print("  %s is exercised by the suite but the report never names it" % m)
    sys.exit(1)

print("SESSION-COVERAGE-PASS (every session regression is named in the report)")
