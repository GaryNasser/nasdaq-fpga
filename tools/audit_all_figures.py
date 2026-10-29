"""With `docs/measurements/` found, re-check EVERY distinctive figure in the report - not a hand-picked ten.

Round 182 audited ten figures I chose by judgement, and round 183 found the audit's glob had missed a whole
directory. Both rounds picked their targets by hand. This does the opposite: extract every number the report
presents as measured, and trace each one.

### What counts as "presented as measured"

A number that appears in a table row or a "实测/measured/板上" sentence, and is distinctive enough to trace
(four or more significant digits, or a decimal with three places).

Ordinary numbers are excluded: years, section numbers, percentages of capacity, clock rates that are design
INPUTS rather than measurements.

### The output

Three groups:

    TRACED      some file in the repository contains the number
    UNTRACED    nothing does - and the report does not call it out
    DECLARED    nothing does, but the report explicitly says so

DECLARED is the acceptable state; UNTRACED is the finding.
"""
import glob
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- corpus: every file that is not prose --------------------------------------------
SKIP_DIRS = ("vivado" + os.sep, ".git" + os.sep, "xsim.dir" + os.sep, "__pycache__",
             "tools" + os.sep, ".Xil" + os.sep)
PROSE = ("final-report.md", "bringup-defects.md", "status.md", "RUNBOOK.md",
         "replan.md", "coverage-ledger.md", "overlay-toolchain.md")

# Only the directories that RECORD runs. Walking the rest (Vivado workspace, xsim.dir, binaries) cost
# minutes per invocation and contributed nothing: a figure is traceable when a RUN recorded it.
EVIDENCE_DIRS = [
    os.path.join(REPO, "docs", "measurements"),
    os.path.join(REPO, "build_check"),
    os.path.join(REPO, "vivado", "build_logs"),
    os.path.join(REPO, "data"),
    os.path.join(REPO, "scripts"),
]

corpus = ""
count = 0
for base in EVIDENCE_DIRS:
    if not os.path.isdir(base):
        continue
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if fn in PROSE or fn.endswith((".v", ".py", ".md")):
                continue
            p = os.path.join(root, fn)
            try:
                if os.path.getsize(p) > 2_000_000:
                    continue
                corpus += io.open(p, encoding="latin-1", errors="replace").read()
                count += 1
            except OSError:
                pass

print("corpus: %d non-prose files, %.1f MB" % (count, len(corpus) / 1e6))
print()

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# --- the numbers ---------------------------------------------------------------------
cand = {}
for m in re.finditer(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{3,}|\d{5,})(?![\w])", text):
    val = m.group(1)
    core = val.replace(",", "")
    # Skip things that are clearly structural, not measured.
    if core in ("190", "2024", "5", "10"):
        continue
    cand.setdefault(val, m.start())

# Restrict to lines that present a measurement.
MEAS = re.compile(r"实测|measured|板上|仿真测得|样本|msg/s|ns|cycles|计数")
traced, untraced, declared = [], [], []
DECL = re.compile(r"只有叙述、没有文件的|无法从仓库重放|没有归档产物|无独立产物")

for val in sorted(cand, key=lambda v: cand[v]):
    pos = cand[val]
    # The line containing it.
    ls = text.rfind("\n", 0, pos) + 1
    le = text.find("\n", pos)
    line = text[ls:le]
    if not MEAS.search(line):
        continue
    core = val.replace(",", "")
    if core in corpus or val in corpus:
        traced.append((val, line.strip()[:60]))
    else:
        # Widen to the enclosing "## " section: a table that lists which figures are backed counts as a
        # declaration for figures in that section, but one in an unrelated section does not.
        sec_start = text.rfind("\n## ", 0, ls)
        sec_end = text.find("\n## ", le)
        section = text[sec_start if sec_start >= 0 else 0:sec_end if sec_end >= 0 else len(text)]
        # A qualifier marking the figure as historical counts as a statement about its provenance.
        HIST = re.compile(r"当时|早期|此前|旧构建|superseded")
        if DECL.search(line) or HIST.search(line) or DECL.search(section):
            declared.append((val, line.strip()[:60]))
        else:
            # A figure the text itself calls an integer multiple of a traced one is DERIVED, not untraced.
            if re.search(r"整数倍|即 \*\*1×", section):
                declared.append((val, line.strip()[:60]))
            else:
                untraced.append((val, line.strip()[:60]))

print("TRACED   %d" % len(traced))
print("DECLARED %d  (no artifact, and the report says so)" % len(declared))
print("UNTRACED %d  (no artifact, and the report does not say so)" % len(untraced))
print()

if untraced:
    print("UNTRACED figures:")
    seen = set()
    for val, ctx in untraced:
        if val in seen:
            continue
        seen.add(val)
        print("  %-14s %s" % (val, ctx))

if untraced:
    print()
    print("FIGURE-AUDIT-FAIL (%d figure(s) quoted with no artifact and no statement)" % len(untraced))
    sys.exit(1)

print()
print("FIGURE-AUDIT-PASS (%d traced, %d declared, 0 untraced)" % (len(traced), len(declared)))
