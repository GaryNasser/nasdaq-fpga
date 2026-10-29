"""Two guards the classifier could not name, and whether they are right.

check_cdc_map.py guards vivado/create_project.tcl
check_provenance_current.py guards the provenance record

The classifier marks both '?' because their path expressions are built with os.path.join
over variables, so the string matching finds nothing to classify.

Whether each is right depends on the same rule as before:

  * create_project.tcl is a BUILD SCRIPT - part of the source tree. Losing it means the
    project cannot be rebuilt, which is a repository defect, not a reason to skip.
  * the provenance record is a BUILD ARTIFACT - produced by a build, absent before one.
    Skipping is correct.

This prints each guard, what it protects, and the verdict the rule gives.
"""
import io
import os
import re
import sys

TOOLS = r"D:\agent\nasdaq-fpga\tools"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CASES = [
    ("check_cdc_map.py", "vivado/create_project.tcl", "BUILD SCRIPT (source tree)"),
    ("check_provenance_current.py", "impl_1/BUILD-PROVENANCE.json", "BUILD ARTIFACT"),
]

print("unclassified guards, resolved by what they protect")
print()

fails = []
for fname, protects, kind in CASES:
    path = os.path.join(TOOLS, fname)
    if not os.path.exists(path):
        print("  %s: missing" % fname)
        continue
    src = io.open(path, encoding="utf-8", errors="replace").read()

    # Find the guard: the print line and the exit that follows.
    m = re.search(r'print\(\s*["\']([A-Z0-9\-]*)(SKIPPED|FAIL)[^"\']*["\'][^)]*\)\s*\n'
                  r'\s*sys\.exit\((\d)\)', src)
    if not m:
        print("  %-30s no guard matched" % fname)
        continue

    token, kindword, code = m.group(1), m.group(2), m.group(3)
    verdict = "skip" if kindword == "SKIPPED" else "fail"
    expected = "fail" if "SCRIPT" in kind else "skip"
    ok = (verdict == expected)

    print("  %-30s protects %-32s (%s)" % (fname, protects, kind))
    print("     guard: %s%s... exit(%s) -> %s" % (token, kindword, code, verdict))
    print("     rule : a %s must %s" % (kind.split(" (")[0].lower(), expected))
    print("     %s" % ("ok" if ok else "WRONG"))
    print()
    if not ok:
        fails.append(fname)

print()
if fails:
    print("UNCLASSIFIED-GUARD-FAIL (%d)" % len(fails))
    for f in fails:
        print("  %s skips what it should fail on, or vice versa" % f)
    sys.exit(1)
print("UNCLASSIFIED-GUARD-PASS (both guards match what they protect)")
