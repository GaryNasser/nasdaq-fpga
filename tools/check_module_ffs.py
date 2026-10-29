"""The report's module FF counts disagreed with every build log the repository holds. Make that checkable.

    report (before this round)   mold64_reasm=650   ts_hist=1353   total 3,507
    rebuild_165.log (actual)     mold64_reasm=715   ts_hist=1355   total 3,565
    rebuild_149..165 (all)       mold64_reasm in 714..725, never 650, never 426

Three separate errors in one parenthetical: two wrong counts, a wrong total, and a derived "426 -> 650 (+52%)"
that describes a transition which never happened. And the round-185 correction built on all of it.

### What this check does

Extracts the `MODULE-FFS:` block from the report, extracts the same block from the CURRENT build log, and requires
them to match. It also recomputes the stated total.

That is a mechanical check for a class of error that has now occurred twice: a figure that traces to SOME artifact
but not to the one the text claims, combined with others in a way that no individual check notices.
"""
import glob
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
LOGS = os.path.join(REPO, "vivado", "build_logs")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

fails = []

# --- the current build's counts -------------------------------------------------------
logs = sorted(glob.glob(os.path.join(LOGS, "rebuild_*.log")),
              key=lambda p: os.path.getmtime(p))
actual = {}
source = None
for p in reversed(logs):
    body = io.open(p, encoding="utf-8", errors="replace").read()
    got = dict(re.findall(r"MODULE-FFS:\s*(\w+)=(\d+)", body))
    if got:
        actual = {k: int(v) for k, v in got.items()}
        source = os.path.basename(p)
        break

if not actual:
    print("DEPLOY-MODFFS-FAIL (no build log contains MODULE-FFS)")
    sys.exit(1)

print("actual module FF counts (%s):" % source)
for k, v in sorted(actual.items()):
    print("  %-14s %d" % (k, v))
print("  %-14s %d" % ("sum", sum(actual.values())))
print()

# --- the report's block ---------------------------------------------------------------
text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

block = re.search(r"```\s*\n(MODULE-FFS:[^`]+)```", text)
if not block:
    print("DEPLOY-MODFFS-FAIL (the report has no MODULE-FFS block)")
    sys.exit(1)

# Both `MODULE-FFS:` lines are in the block, and each carries TWO name=value pairs. Strip the prefix
# and findall every assignment, or only the first pair per line is seen (round 186: this reported a
# 1495 total against a stated 3565 and looked like the report was wrong).
_body = re.sub(r"MODULE-FFS:\s*", " ", block.group(1))
stated = dict(re.findall(r"(\w+)=(\d+)", _body))
stated = {k: int(v) for k, v in stated.items()}

print("report states:")
for k, v in sorted(stated.items()):
    mark = "" if actual.get(k) == v else "  <- DIFFERS, actual %s" % actual.get(k)
    print("  %-14s %d%s" % (k, v, mark))
    if actual.get(k) != v:
        fails.append("%s is %d in the report but %d in %s" % (k, v, actual.get(k), source))

# --- the stated total -----------------------------------------------------------------
m = re.search(r"合计\s*\*\*([\d,]+)\*\*", text)
if m:
    total = int(m.group(1).replace(",", ""))
    real = sum(stated.values())
    print("  %-14s %d  (its own four counts sum to %d)%s"
          % ("stated total", total, real, "" if total == real else "  <- DOES NOT ADD UP"))
    if total != real:
        fails.append("the stated total %d is not the sum of the four counts (%d)" % (total, real))
else:
    print("  stated total: not found")

print()
if fails:
    print("DEPLOY-MODFFS-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)

print("DEPLOY-MODFFS-PASS (the report's module counts match the current build and add up)")
