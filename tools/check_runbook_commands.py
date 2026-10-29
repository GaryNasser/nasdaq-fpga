"""Do the runbook's commands actually exist and parse?

Round 72 checked that the runbook's NUMBERS match their sources. It did not check that the
COMMANDS can be executed: a path that moved, a flag that was renamed, or a script that
takes different arguments would all pass a number check.

An operator following the runbook under time pressure should not discover that
`python tools/board_recover.py --check` takes a different flag than documented.

This parses every `python <path> <flags>` line out of the runbook and verifies:
  * the script exists;
  * each documented flag appears in that script's argparse (or in the driver it wraps);
  * no flag is documented that the script would reject.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
DOC = os.path.join(REPO, "docs", "RUNBOOK.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(DOC):
    print("RUNBOOK-CMD-FAIL (no runbook)")
    sys.exit(1)

doc = io.open(DOC, encoding="utf-8").read()

# Commands appear inside fenced sh blocks, sometimes with a trailing comment.
CMD = re.compile(r"^\s*python\s+([\w./\\-]+\.py)\s*([^\n#]*)", re.M)

print("commands cited by the runbook")
print()
fails = []
seen = 0

for m in CMD.finditer(doc):
    script, args = m.group(1).strip(), m.group(2).strip()
    rel = script.replace("/", os.sep)
    path = os.path.join(REPO, rel)

    exists = os.path.exists(path)
    flags = re.findall(r"--[\w-]+", args)
    seen += 1

    print("  %-38s %s" % (script, "exists" if exists else "*** MISSING ***"))
    if args:
        print("      args: %s" % args[:70])
    if not exists:
        fails.append("the runbook cites %s, which does not exist" % script)
        continue

    if not flags:
        continue

    src = io.open(path, encoding="utf-8", errors="replace").read()
    # A wrapper may forward to another script; check both.
    forwarded = re.findall(r'"([\w./\\-]+\.py)"', src)
    corpus = src
    for f in forwarded:
        p2 = os.path.join(REPO, "tools", os.path.basename(f))
        if os.path.exists(p2):
            corpus += io.open(p2, encoding="utf-8", errors="replace").read()

    for fl in flags:
        accepted = (('"' + fl + '"') in corpus) or (("'" + fl + "'") in corpus)
        print("      %-16s accepted: %s" % (fl, accepted))
        if not accepted:
            fails.append("%s is documented with %s, but that script does not define it"
                         % (script, fl))

print()
print("  %d command(s) cited" % seen)
print()
if fails:
    print("RUNBOOK-CMD-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
if seen == 0:
    print("RUNBOOK-CMD-FAIL (no python commands found - the scan would be vacuous)")
    sys.exit(1)
print("RUNBOOK-CMD-PASS (every cited command and flag is real)")
