"""Assert that simulation runs are archived, and that the archive contains the figures the report quotes.

Round 182's finding was that ten headline figures had no artifact. Round 183 made `run_sims.py` archive every
simulator invocation. **A mechanism nobody checks decays** - the next edit to `sh()` could drop the archive
call and nothing would notice until a figure was challenged again.

### What this checks

    1  run_sims.py still calls the archiver from sh()
    2  build_check/sim_runs/ exists and holds at least one run
    3  some archived log contains the simulated T1 sample count (19969 / 19,969)

(3) is the specific one worth having: it is the figure the report quotes, and its presence in an archived log is
what makes it re-derivable.
"""
import glob
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RUNNER = os.path.join(REPO, "tools", "run_sims.py")
ARCHIVE = os.path.join(REPO, "build_check", "sim_runs")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

fails = []

runner = io.open(RUNNER, encoding="utf-8").read()
has_call = "_archive(cmd" in runner
print("  archiver wired into sh():      %s" % has_call)
if not has_call:
    fails.append("run_sims.sh() no longer archives its output")

runs = sorted(d for d in glob.glob(os.path.join(ARCHIVE, "*")) if os.path.isdir(d))
print("  archived run directories:      %d" % len(runs))
if not runs:
    fails.append("no archived run directories - run tools/run_sims.py once")
else:
    # Round 18: the newest directory can be a run that was INTERRUPTED (46 logs against a
    # complete run's 111). Asking the newest run for a figure it never got to print reports a
    # failure of the archive when the real cause is a killed suite. Take the newest COMPLETE run.
    def _logs(d):
        return glob.glob(os.path.join(d, "*.log"))

    complete = [d for d in runs if len(_logs(d)) >= 100]
    latest = (complete or runs)[-1]
    logs = _logs(latest)
    skipped = [os.path.basename(d) for d in runs if d not in complete]
    print("  newest complete run %s: %d log(s)" % (os.path.basename(latest), len(logs)))
    if skipped:
        print("  ignored incomplete run(s): %s" % ", ".join(skipped[-4:]))
    if not logs:
        fails.append("the newest run directory is empty")

    # Does any archived log hold the T1 sample count the report quotes?
    needle = re.compile(r"19,?969")
    hit = None
    for p in logs:
        try:
            if needle.search(io.open(p, encoding="utf-8", errors="replace").read()):
                hit = os.path.basename(p)
                break
        except Exception:
            pass
    print("  an archived log holds 19969:   %s" % (hit or "NOT FOUND"))
    if not hit:
        fails.append("no archived log contains the simulated T1 sample count (19969)")

print()
if fails:
    print("SIM-ARCHIVE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)

print("SIM-ARCHIVE-PASS (runs are archived and the quoted T1 figure is in them)")
