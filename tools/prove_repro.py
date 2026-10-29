"""Prove all three assertions in check_repro_doc.

Read from the source (L63-L76), it fails when:

    a suite check is not documented in section 9.0        `missing`
    a documented check is no longer in the suite          `stale`
    the stated total differs from the actual count        `stated != len(implemented)`

**These are three different drift modes** and the report has hit all three: round 80-15 added 15 checks nobody
documented; and the total has been refreshed every round since.

The first is invisible to the second, so each needs its own injection.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
RUNNER = os.path.join(REPO, "tools", "run_checks.py")
CHK = os.path.join(REPO, "tools", "check_repro_doc.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("REPRO-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

results = []


def inject(label, path, transform):
    body = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    mutated = transform(body)
    if mutated == body:
        print("  %-38s INCONCLUSIVE (no change)" % label)
        results.append(None)
        return
    bk = tempfile.mktemp(suffix=".md")
    shutil.copyfile(path, bk)
    try:
        io.open(path, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
        rc, _ = run()
    finally:
        shutil.copyfile(bk, path)
        os.unlink(bk)
    caught = rc != 0
    results.append(caught)
    print("  %-38s exit=%-3d %s" % (label, rc, "CAUGHT" if caught else "MISSED"))


# 1  A suite check with no documentation row.
inject("undocumented check added to the suite", RUNNER, lambda s: s.replace(
    "CHECKS = [", 'CHECKS = [\n    ("zz_undocumented", "a check nobody documented", False),', 1))

# 2  A documented check that is not in the suite. It must go INSIDE section 9.0: the check scans
# only the segment between "### 9.0" and "### 9.0b" (L33-L36), so a row before that heading is invisible.
GHOST_ROW = '| `zz_ghost` | a check that is not in the suite | x | `GHOST` |\n'
inject("documented row for a check that does not run", REPORT,
       lambda s: s.replace("### 9.0b", GHOST_ROW + "### 9.0b", 1))

# 3  The stated total no longer matches.
def bump_total(s):
    return re.sub(r"passed (\d+), failed 0, skipped 0(, pending \d+)? of (\d+)",
                  lambda m: "passed %s, failed 0, skipped 0 of %d"
                            % (m.group(1), int(m.group(3)) + 1), s, count=1)


inject("stated total off by one", REPORT, bump_total)

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)

caught = sum(1 for c in results if c)
total = sum(1 for c in results if c is not None)
print()
if total and caught == total and rc2 == 0:
    print("REPRO-PROOF-PASS (%d/%d drift modes caught)" % (caught, total))
    sys.exit(0)
print("REPRO-PROOF-FAIL (%d of %d caught)" % (caught, total))
sys.exit(1)
