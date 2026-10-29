"""Verify that the converted skip guards really fail when their input is absent.

Round 61 turned eleven `if not exists: SKIPPED; exit(0)` guards into failures. This proves
the conversion took effect, by removing the report and requiring every report-guarded
checker to fail.

The subject list is explicit rather than inferred. Three attempts to infer it from source
went wrong in three ways - picking up files that merely mention the report, including this
check (which deletes the report and would fail for the reason it tests), and a structural
regex that matched nothing and silently shrank the test to zero subjects.

A misplaced name is visible: running a listed checker against a missing report either fails
(guard works) or does not (guard lost), and both are reported.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Checkers that guard docs/final-report.md and must fail without it.
SUBJECTS = [
    "check_build_figures.py",
    "check_busyrun_direction.py",
    "check_dma_claim.py",
    "check_hw_provenance.py",
    "check_limits_section.py",
    "check_margin_disclosure.py",
    "check_recover_semantics.py",
    "check_t1_sets.py",
    "check_throughput_pair.py",
    "check_timing_reconcile.py",
    "check_wns_ownership.py",
]

print("report guards, exercised against a absent report")
print()

present = [s for s in SUBJECTS if os.path.exists(os.path.join(TOOLS, s))]
missing = [s for s in SUBJECTS if s not in present]
for s in missing:
    print("  %-34s listed but NOT PRESENT in tools/" % s)

if not present:
    print()
    print("SKIP-CONVERSION-FAIL (none of the listed checkers exist)")
    sys.exit(1)

if not os.path.exists(REPORT):
    print()
    print("SKIP-CONVERSION-FAIL (no report to remove)")
    sys.exit(1)

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
original = open(REPORT, "rb").read()

results = []
try:
    os.remove(REPORT)
    for name in present:
        r = subprocess.run([sys.executable, os.path.join(TOOLS, name)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        ok = (r.returncode != 0) and ("FAIL" in out)
        results.append((name, ok, r.returncode))
finally:
    open(REPORT, "wb").write(original)
    os.unlink(backup)

for name, ok, rc in results:
    print("  %-34s exit %-2d %s" % (name, rc, "FAIL" if ok else "STILL PASSES"))

restored = open(REPORT, "rb").read() == original
print()
print("  report restored: %s" % restored)

bad = [n for n, ok, _ in results if not ok]
print()
if bad:
    print("SKIP-CONVERSION-FAIL (%d)" % len(bad))
    for n in bad:
        print("  %s did not fail with the report absent" % n)
    sys.exit(1)
if missing:
    print("SKIP-CONVERSION-FAIL (%d listed checker(s) missing)" % len(missing))
    sys.exit(1)
if not restored:
    print("SKIP-CONVERSION-FAIL (report not restored)")
    sys.exit(1)
print("SKIP-CONVERSION-PASS (%d report guard(s) verified to fail)" % len(results))
