"""Confirm a missing report now FAILS instead of skipping.

The change this round: eight checkers that guard docs/final-report.md used to exit 0 when
it was absent. Now they exit 1.

Test: rename the report temporarily, run three of those checkers, require a non-zero exit,
restore, require zero. This exercises the real guard rather than reading the source.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHECKS = [
    "check_t1_sets.py",
    "check_wns_ownership.py",
    "check_margin_disclosure.py",
]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
original = open(REPORT, "rb").read()

os.remove(REPORT)
results = []
try:
    for name in CHECKS:
        r = subprocess.run([sys.executable, os.path.join(REPO, "tools", name)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        failed = (r.returncode != 0) and ("FAIL" in out)
        results.append((name, r.returncode, failed))
        print("  %-32s report absent -> exit %d %s"
              % (name, r.returncode, "FAIL" if failed else "still passing"))
finally:
    open(REPORT, "wb").write(original)
    os.unlink(backup)

restored = open(REPORT, "rb").read() == original
print()
print("  restored: %s" % restored)

healthy = []
for name in CHECKS:
    r = subprocess.run([sys.executable, os.path.join(REPO, "tools", name)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    healthy.append((name, r.returncode))
    print("  %-32s report present -> exit %d" % (name, r.returncode))

print()
if all(f for _, _, f in results) and restored and all(rc == 0 for _, rc in healthy):
    print("REPORT-REQUIRED-PASS (a missing report fails the checks that read it)")
else:
    print("REPORT-REQUIRED-FAIL")
    sys.exit(1)
