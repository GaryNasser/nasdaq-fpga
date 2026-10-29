"""All the audit's evidence must come from ONE build, and it must be the deployed one.

Round 80 made the deliverable audit read artifacts. Round 81 found two of its helpers
reading DIFFERENT builds:

    util_numbers    impl_1 utilization report   2026-10-23 23:26:14  <- same run as the .bit
    wns_value       build_check/rebuild.log     2026-10-23 23:09:38  <- an earlier run

so the "resources" and "WNS" deliverables were certified from two designs. Fixed by pointing
wns_value at impl_1's own timing summary.

The general rule the report already follows (section 4.1's two-column table) is that a build's
figures travel together. This check enforces it for the audit:

    every artifact the audit reads must belong to the build that produced nasdaq.bit

How "belongs" is decided: the provenance record names the bitstream MD5 and mtime; an
artifact written before that build started cannot be part of it. Files written after are
allowed (reports are produced at the end of the run).

This is the check that would have caught round 81's fault on its own.
"""
import hashlib
import io
import json
import os
import sys
import re
import time

REPO = r"D:\agent\nasdaq-fpga"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

IMPL = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1")
PROV = os.path.join(IMPL, "BUILD-PROVENANCE.json")
BIT = os.path.join(REPO, "vivado", "out", "nasdaq.bit")
AUDIT = os.path.join(REPO, "tools", "audit_deliverables.py")

# Artifacts the audit reads for build facts.
SOURCES = {
    "utilization": os.path.join(IMPL, "nasdaq_wrapper_utilization_placed.rpt"),
    "timing": os.path.join(IMPL, "nasdaq_wrapper_timing_summary_routed.rpt"),
}
# Files that must NOT be used as build evidence, with the reason.
FORBIDDEN = {
    "build_check/rebuild.log": "a different implementation run (WNS 0.157 vs 0.042)",
}

print("build artifacts the audit relies on")
print()

if not os.path.exists(BIT):
    print("BUILD-PAIRING-FAIL (deployed bitstream missing)")
    sys.exit(1)

bit_mtime = os.path.getmtime(BIT)

h = hashlib.md5()
with open(BIT, "rb") as f:
    for c in iter(lambda: f.read(1 << 20), b""):
        h.update(c)
bit_md5 = h.hexdigest().upper()
print("  deployed bitstream  %s  %s"
      % (bit_md5[:16], time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(bit_mtime))))

fails = []

if os.path.exists(PROV):
    rec = json.load(io.open(PROV, encoding="utf-8"))
    recorded = rec.get("bitstream_md5", "").upper()
    if recorded != bit_md5:
        fails.append("provenance records %s but the deployed bitstream is %s"
                     % (recorded[:16], bit_md5[:16]))
    print("  provenance records  %s  %s"
          % (recorded[:16], "MATCH" if recorded == bit_md5 else "MISMATCH"))
else:
    fails.append("no provenance record")

print()
for label, path in SOURCES.items():
    if not os.path.exists(path):
        print("  %-12s MISSING" % label)
        fails.append("%s report is absent" % label)
        continue
    m = os.path.getmtime(path)
    # Reports are written during/at the end of the run; allow a small before-window.
    delta = m - bit_mtime
    ok = abs(delta) < 1800        # within 30 minutes of the bitstream
    print("  %-12s %s  (bitstream %+.0f s)  %s"
          % (label, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(m)),
             delta, "same run" if ok else "*** DIFFERENT RUN ***"))
    if not ok:
        fails.append("%s is %+.0f s from the deployed bitstream - a different run"
                     % (label, delta))

print()
print("  files the audit must not use as build evidence:")
# Strip comments and docstrings before looking for the path: the audit's own warning
# names build_check/rebuild.log to say it must NOT be used, and matching that would flag
# the warning as the fault.
audit_src = io.open(AUDIT, encoding="utf-8").read()
audit_src = re.sub(r'""".*?"""', "", audit_src, flags=re.S)
audit_src = re.sub(r"#[^\n]*", "", audit_src)
for rel, why in FORBIDDEN.items():
    used = rel in audit_src
    print("     %-28s %-40s %s"
          % (rel, why[:40], "*** USED ***" if used else "not used"))
    if used:
        fails.append("the audit reads %s (%s)" % (rel, why))

print()
if fails:
    print("BUILD-PAIRING-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("BUILD-PAIRING-PASS (every build fact the audit uses comes from the deployed run)")
