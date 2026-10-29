"""Which directories holding deliverables are still outside version control?

Round 208 found `docs/` (192 files, including the report) was gitignored wholesale. The same question applies to
every other directory: is the thing it holds a deliverable or a build product?

### The distinction

    deliverable     source, documentation, evidence, small data   -> must be tracked
    build product   bitstreams, workspace, captures, caches       -> ignored is right

A build product can be regenerated; a deliverable cannot. `docs/measurements/` is evidence - it is a deliverable
even though it looks like output, because the board cannot be re-run to order.
"""
import io
import os
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def git(*a):
    return subprocess.run(["git"] + list(a), capture_output=True, text=True, cwd=REPO,
                          encoding="utf-8", errors="replace")


tracked = set(git("ls-files").stdout.split("\n"))

# Top-level directories, with whether ignore is defensible.
EXPECT = {
    "rtl":         ("deliverable", "the design"),
    "tools":       ("deliverable", "the checks and benches"),
    "docs":        ("deliverable", "the report and the evidence"),
    "vivado":      ("mixed", "tcl sources yes; workspace/ and out/ are build products"),
    "scripts":     ("deliverable", "build and deploy flow"),
    "data":        ("product", "multi-MB captures; regenerable by download or pack"),
    "build_check": ("product", "archived baselines; large binaries"),
    "smoke":       ("deliverable", "smoke test"),
    # specs/ is ignored BY THE USER'S REQUEST (.gitignore:44). The build script cites it; the
    # repository deliberately does not contain it. Recorded, not fixed.
    "specs":       ("intentional", "user requires specs stay local"),
}

print("%-14s %-12s %6s %6s  %s" % ("dir", "kind", "files", "tracked", "verdict"))
print("-" * 86)

problems = []
for d in sorted(os.listdir(REPO)):
    p = os.path.join(REPO, d)
    if not os.path.isdir(p) or d.startswith(".git"):
        continue
    n = sum(len(fs) for _r, _dd, fs in os.walk(p))
    t = sum(1 for f in tracked if f.startswith(d + "/"))
    kind, why = EXPECT.get(d, ("unknown", ""))
    DELIBERATE = {'.playwright-mcp': 'browser tooling scratch, unrelated to the design', 'dist': 'packaging output of tools/make_package.py; regenerated on demand, never tracked', '.Xil': 'Vivado scratch', '.claude': 'agent config', '.specify': 'user requires specs tooling stays local', 'NA': 'Vivado-generated HTML', 'board': 'deploy helpers; tracked files exist, pycache ignored', 'sw': 'driver sources; already tracked', 'specs': 'user requires specs stay local', 'xsim.dir': 'simulator objects'}
    if kind == "unknown" and d in DELIBERATE:
        kind, verdict = "intentional", "intentional: " + DELIBERATE[d]
    elif kind == "unknown":
        verdict = "UNCLASSIFIED"
        problems.append((d, n, t, verdict))
    elif kind in ("deliverable", "mixed") and t == 0 and kind != "intentional":
        verdict = "NOT TRACKED"
        problems.append((d, n, t, verdict))
    elif kind == "mixed" and t == 0:
        verdict = "NOT TRACKED"
        problems.append((d, n, t, verdict))
    else:
        verdict = "ok"
    if n or t:
        print("%-14s %-12s %6d %6d  %s" % (d[:14], kind, n, t, verdict))

print()
_untracked = [p for p in problems if p[3] in ("NOT TRACKED", "UNCLASSIFIED")]
print("untracked deliverable directories: %d" % len(_untracked))
for d, n, t, v in problems:
    print("  %-16s %d files, %d tracked   %s" % (d, n, t, v))

# And the reverse: build products that ARE tracked (bloating the repo).
print()
print("tracked build products (should probably be ignored):")
for f in sorted(tracked):
    if any(f.startswith(x) for x in ("vivado/workspace/", "build_check/", "data/")):
        print("  " + f)
        break
else:
    print("  none")

r = git("count-objects", "-vH")
print()
print("repository size:")
for l in (r.stdout or "").split("\n"):
    if l.strip():
        print("  " + l.strip())

if _untracked:
    print()
    print("TRACKING-AUDIT-FAIL (%d)" % len(_untracked))
    print("  Every directory holding files must be either tracked or explicitly classified.")
    print("  Add it to EXPECT or DELIBERATE with the reason.")
    sys.exit(1)

print()
print("TRACKING-AUDIT-PASS (every directory is tracked or deliberately not)")
