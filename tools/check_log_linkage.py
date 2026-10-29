"""A newly registered check must be mentioned in the defect log in the same commit.

Round 23 found the log nine rounds behind and 25 primary checks with no recorded reason to exist. Requiring every
historical check to be back-filled would mean inventing provenance I no longer have - and an invented record is worse
than an absent one.

So the rule is forward-only: **a check registered from now on must appear in the log.** The existing 25 are listed in
`docs/known-gaps.md` rather than silently passed over.

This reads a snapshot of the check names taken at round 23 and fails only on additions.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
LOG = os.path.join(REPO, "docs", "bringup-defects.md")
RUNNER = os.path.join(REPO, "tools", "run_checks.py")
BASELINE = os.path.join(REPO, "tools", "log_linkage_baseline.txt")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

log = io.open(LOG, encoding="utf-8", errors="surrogateescape").read()
runner = io.open(RUNNER, encoding="utf-8").read()
names = sorted(set(re.findall(r'^\s*\("(\w+)",', runner, re.M)))
primary = [n for n in names
           if not n.endswith("_proof") and not n.startswith("prove_") and not n.startswith("mutate_")]

if not os.path.exists(BASELINE):
    print("LOG-LINKAGE-FAIL: no baseline snapshot - run tools/snapshot_links.py once")
    sys.exit(1)

known = set(l.strip() for l in
            io.open(BASELINE, encoding="utf-8").read().split("\n") if l.strip())
print("primary checks        : %d" % len(primary))
print("in the baseline       : %d" % len(known))

added = [n for n in primary if n not in known]
print("added since round 23  : %d" % len(added))

unlogged = [n for n in added if n not in log]
print("added but not in log  : %d" % len(unlogged))
print()

if unlogged:
    for n in unlogged:
        print("  %s" % n)
    print()
    print("LOG-LINKAGE-FAIL (%d new check(s) with no entry in the defect log)" % len(unlogged))
    print("  A check whose reason lives only in a commit message is one a later reader deletes.")
    sys.exit(1)

print("LOG-LINKAGE-PASS (every check added since round 23 has a log entry)")
