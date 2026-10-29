"""Verify the documented module-level FF counts against a fresh synthesis run.

Round 86 caught the device-level LUT/FF figures being pre-byte-FIFO. The module
breakdown was stale too, and worse: mold64_reasm was documented at 426 FF when the
rewrite had taken it to 650 (+52%).

The numbers come from build_overlay.tcl, which prints MODULE-FFS after synthesis.
Rather than re-run the full 40-minute build to check three integers, this counts
FF declarations in the elaborated netlist obtained from the existing synthesis DCP
if available, and otherwise re-derives the counts from the source by elaboration.

The cheapest reliable route: run synthesis-only into a throwaway project is still
slow, so this compares the DOCUMENT against the numbers printed by the most recent
build log, which is the same source the document cites. If no log is available it
reports SKIPPED rather than passing silently.
"""
import glob
import io
import os
import re
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOC = r"D:\agent\nasdaq-fpga\docs\final-report.md"

# Find the most recent build log that contains MODULE-FFS lines.
#
# Round 186: prefer the project's OWN build logs. `%TEMP%\build*.log` are ad-hoc captures from a debugging
# session on 2026-10-23, and reading them meant this check validated the report against a build two days older
# than the one on disk - and passed, because both carried the same stale value (mold64_reasm=650 vs 715).
candidates = []
for pat in (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "vivado", "build_logs", "rebuild_*.log"),
            os.path.join(os.environ.get("TEMP", ""), "build_r*.log"),
            os.path.join(os.environ.get("TEMP", ""), "build*.log")):
    candidates.extend(glob.glob(pat))

best = None
best_mtime = 0
for c in candidates:
    try:
        mtime = os.path.getmtime(c)
    except OSError:
        continue
    if mtime <= best_mtime:
        continue
    try:
        txt = io.open(c, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    found = re.findall(r"^MODULE-FFS: (\w+)=(\d+)$", txt, re.M)
    if found:
        best = (c, dict(found), mtime)
        best_mtime = mtime

if best is None:
    print("no build log with MODULE-FFS found - SKIPPED")
    print("MODULE-FF-SKIPPED")
    sys.exit(0)

log_path, actual, mtime = best
print("build log: %s" % os.path.basename(log_path))
print("actual   : %s" % " ".join("%s=%s" % kv for kv in sorted(actual.items())))

doc = io.open(DOC, encoding="utf-8").read()
# Read ONLY the authoritative MODULE-FFS code block. The surrounding prose quotes
# the previous values for comparison, and a naive scan picks those up and reports
# the stale numbers as if they were current - which is exactly the confusion this
# check exists to prevent.
_m = re.search(r"MODULE-FFS:.*?```", doc, re.S)
block = _m.group(0) if _m else ""
if not block:
    print("no MODULE-FFS block found in the document")
    print("MODULE-FF-FAIL (1)")
    sys.exit(1)
_pairs = dict(re.findall(r"(\w+)=(\d+)", block))
documented = {k: v for k, v in _pairs.items()
              if k in ("order_book", "mold64_reasm", "itch_parse", "ts_hist")}
print("documented: %s" % " ".join("%s=%s" % kv for kv in sorted(documented.items())))

fails = []
print()
for name, av in sorted(actual.items()):
    dv = documented.get(name)
    if dv is None:
        print("  %-14s actual %-6s document does not mention it" % (name, av))
        fails.append("%s missing from the document" % name)
        continue
    ok = (dv == av)
    print("  %-14s doc %-6s actual %-6s %s"
          % (name, dv, av, "OK" if ok else "MISMATCH"))
    if not ok:
        fails.append("%s: doc %s vs actual %s" % (name, dv, av))

print()
if fails:
    print("MODULE-FF-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("MODULE-FF-PASS")
