"""Which skips are legitimate, and which hide a missing tool input?

The 22 skips fall into three classes:

  BUILD ARTIFACT   impl_1 reports, bitstream, provenance, XDC, build logs.
                   Absent on a fresh clone. Skipping is right - the suite must not be
                   red before the first build.

  REPORT           docs/final-report.md.
                   If this is missing, the deliverable is missing. Skipping every
                   document check would leave the suite green with no report at all.

  TOOL INPUT       a script the checker reads, e.g. test_golden_exit reading
                   test_input_probe.py. If that disappears, the checker is broken, not
                   the project - and a silent skip hides it.

Class 2 and 3 are the problem. This classifies every skip by which file it guards, so the
distinction is visible instead of assumed.
"""
import glob
import io
import os
import re
import sys

TOOLS = r"D:\agent\nasdaq-fpga\tools"
REPO = r"D:\agent\nasdaq-fpga"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# A guard is a SKIP only if its token says SKIPPED and its exit is 0. A token like
# "SKIP-CONVERSION-FAIL" starts with SKIP but reports a failure, and a "*-SKIPPED" token
# followed by exit(1) is a converted guard. Judging on both the verdict word and the exit
# code avoids reading a name as a behaviour.
SKIP = re.compile(r'print\(\s*["\'][A-Z0-9\-]*SKIPPED')

# Resolve the constant names each checker guards.
def guarded_constants(src):
    out = []
    for m in re.finditer(r"if\s+not\s+os\.path\.exists\((\w+)\)", src):
        name = m.group(1)
        # find its definition
        d = re.search(r"^%s\s*=\s*(.+)$" % re.escape(name), src, re.M)
        out.append((name, d.group(1).strip() if d else "?"))
    return out


def classify(value):
    v = value.lower()
    if "final-report" in v or "status.md" in v or "bringup" in v:
        return "REPORT"
    if any(k in v for k in ("rtl", "board/", "tools/", "load_overlay", "test_")):
        return "TOOL/RTL"
    if any(k in v for k in ("workspace", "impl_1", "build_check", ".xdc", ".bit",
                            ".log", "provenance", ".json")):
        return "BUILD"
    return "?"


print("skip guards classified by what they protect")
print()
counts = {}
problems = []
for path in sorted(glob.glob(os.path.join(TOOLS, "check_*.py"))):
    name = os.path.basename(path)
    src = io.open(path, encoding="utf-8", errors="replace").read()
    # Strip comments and docstrings before looking for the guard. Without this, a file
    # that merely DISCUSSES the pattern - including this one's neighbours - looks like it
    # contains it. Rounds 62-65 lost mutations to exactly this; now it is in a checker.
    code = re.sub(r"\"\"\".*?\"\"\"", "", src, flags=re.S)
    code = re.sub(r"'''.*?'''", "", code, flags=re.S)
    code = re.sub(r"#[^\n]*", "", code)
    if not SKIP.search(code):
        continue
    for const, value in guarded_constants(src):
        cls = classify(value)
        counts[cls] = counts.get(cls, 0) + 1
        short = value if len(value) < 60 else value[:57] + "..."
        print("  %-30s %-10s %s" % (name, cls, short))
        if cls in ("REPORT", "TOOL/RTL"):
            problems.append((name, cls, short))

print()
for k in ("BUILD", "REPORT", "TOOL/RTL", "?"):
    if k in counts:
        print("  %-10s %d" % (k, counts[k]))

print()
if problems:
    print("SKIP-CLASS-FAIL (%d skip(s) hide a missing deliverable or tool)" % len(problems))
    for n, c, v in problems:
        print("  %-30s %-10s %s" % (n, c, v))
    sys.exit(1)
print("SKIP-CLASS-PASS (skips guard build artifacts only)")
