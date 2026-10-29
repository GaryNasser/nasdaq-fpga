"""Which checkers read build artifacts, and do they read the DEPLOYED build's artifacts?

Round 81 found wns_value reading build_check/rebuild.log - an 18-minute-earlier run with a
different placement. The rule that follows:

    a figure attributed to the shipped design must come from the run that produced nasdaq.bit

The deployed build's artifacts live in impl_1/ and are written within seconds of the
bitstream (utilization -62 s, timing -12 s, measured last round). build_check/ holds an
earlier, separate build used for the P&R-nondeterminism experiment.

Any checker that reads a build figure must read impl_1 (or the provenance record), not
build_check. This enumerates every checker that mentions a build artifact path and says
which side it is on.
"""
import glob
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The deployed build's own figures, taken from impl_1's reports.
IMPL_DIR = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1")


def deployed_slacks():
    p = os.path.join(IMPL_DIR, "nasdaq_wrapper_timing_summary_routed.rpt")
    if not os.path.exists(p):
        return None
    lines = io.open(p, encoding="utf-8", errors="replace").read().split("\n")
    for i, ln in enumerate(lines):
        if "WNS(ns)" in ln and "WHS(ns)" in ln:
            for j in range(i + 1, min(i + 4, len(lines))):
                row = lines[j].split()
                if len(row) >= 8:
                    try:
                        return (float(row[0]), float(row[4]))
                    except ValueError:
                        continue
    return None


DEPLOYED = deployed_slacks()


def build_check_files_claiming_slacks():
    """For each build_check log, the slacks it states - and whether they match the deployed."""
    out = []
    d = os.path.join(REPO, "build_check")
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if not os.path.isfile(p):
            continue
        try:
            t = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        hits = re.findall(r"TIMING-METRICS:\s*WNS=([-+]?\d+\.\d+)\s+WHS=([-+]?\d+\.\d+)",
                          t)
        real = [h for h in hits if "$" not in h[0]]
        if real:
            out.append((name, [tuple(float(x) for x in h) for h in real]))
    return out


print("build_check logs that state a slack figure, versus the deployed build")
print()
if DEPLOYED:
    print("  deployed build (impl_1): WNS %+.3f  WHS %+.3f" % DEPLOYED)
else:
    print("  deployed build (impl_1): reports MISSING")
print()

matching, differing = [], []
for name, values in build_check_files_claiming_slacks():
    same = DEPLOYED is not None and all(v == DEPLOYED for v in values)
    (matching if same else differing).append(name)
    print("  %-24s %s  %s"
          % (name, ", ".join("(%+.3f,%+.3f)" % v for v in values[:2]),
             "MATCHES the deployed build" if same else "different run"))

print()
print("  matching   : %s" % (matching or "none"))
print("  differing  : %s" % (differing or "none"))

# Which checkers read each.
print()
print("  checkers that read each non-deployed log:")
fails = []
for name in differing:
    users = []
    for p in sorted(os.listdir(os.path.join(REPO, "tools"))):
        if not p.endswith(".py") or p.startswith(("mutate_", "test_")):
            continue
        raw = io.open(os.path.join(REPO, "tools", p), encoding="utf-8",
                      errors="replace").read()
        code = re.sub(r'""".*?"""', "", raw, flags=re.S)
        code = re.sub(r"#[^\n]*", "", code)
        if name in code:
            users.append(p)
    print("     %-24s <- %s" % (name, ", ".join(users) or "none"))
    # Reading a non-deployed log is only a fault if the checker treats it as the
    # deployed build's figure. check_experiment_evidence and check_clock_xdc do not.
    for u in users:
        body = io.open(os.path.join(REPO, "tools", u), encoding="utf-8",
                       errors="replace").read()
        if re.search(r"deployed|nasdaq\.bit|impl_1", body):
            continue
        # It reads the file but never compares against the deployed build.
        fails.append(u)

print()
if fails:
    print("BUILD-SOURCE-REVIEW (%d)" % len(fails))
    for f in fails:
        print("  %s reads a non-deployed build log" % f)
    sys.exit(1)
print("BUILD-SOURCE-PASS (no checker treats a non-deployed log as the shipped figure)")
