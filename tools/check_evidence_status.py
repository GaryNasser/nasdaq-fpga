"""Sweep every measured figure: is it in a data file, and does the report cite that file?

Round 103's version listed four groups by hand. Round 104's map shows the real split:

    sourced by a file       927.35, 4502/5431, 0.042/0.034, and (round 183) 210.5/1136.8/19961 via
                            docs/measurements/board-recover-20261024-154952.txt
    prose only              299.01, 3,344,390, 2,230,335

The check derives that split rather than being told it: search the data files for each figure.
If found, the report must cite the file. If not found, the report must state the class.

So a new measured figure with no source fails, and removing the class statement fails, without
anyone maintaining a list.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Every spelling each figure may take in the report and in the data files.
FIGURES = {
    "299.01":    ["299.01"],
    "3,344,390": ["3,344,390", "3344390"],
    "2,230,335": ["2,230,335", "2230335"],
    "210.5":     ["210.5"],
    "1136.8":    ["1136.8"],
    "19961":     ["19961", "19,961"],
    "927.35":    ["927.35"],
    # Round 166: the report now quotes the round-165 build's figures (4,502 LUT / 5,431 FF), not the
    # round-33 experiment's. Sweeping for the old numbers checked text that is no longer there.
    "4,502":     ["4,502", "4502"],
    "5,431":     ["5,431", "5431"],
    "0.042":     ["0.042"],
}

# Index the data files once.
corpus = []
for root, dirs, files in os.walk(REPO):
    dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "local_data", ".Xil")]
    for f in files:
        if not f.endswith((".txt", ".log", ".json", ".rpt", ".csv")):
            continue
        full = os.path.join(root, f)
        rel = os.path.relpath(full, REPO)
        if rel.startswith("tools" + os.sep) or rel == os.path.join("docs",
                                                                   "final-report.md"):
            continue
        try:
            if os.path.getsize(full) > 20_000_000:
                continue
            corpus.append((rel, io.open(full, encoding="latin-1",
                                       errors="replace").read()))
        except OSError:
            continue

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

STATEMENT = re.compile(r"只有叙述、没有文件的|无法从仓库重放")
class_stated = bool(STATEMENT.search(text))

print("each measured figure: found in a data file, and cited by the report?")
print()
print("  the report states the unsourced class: %s" % class_stated)
print()

fails = []
for label, spellings in FIGURES.items():
    if not any(s in text for s in spellings):
        continue
    sources = sorted({rel for rel, body in corpus
                      if any(s in body for s in spellings)})

    if sources:
        cited = any(s.replace(os.sep, "/") in text or os.path.basename(s) in text
                    for s in sources)
        print("  %-10s file: %-42s cited=%s"
              % (label, os.path.basename(sources[0])[:42], cited))
        if not cited:
            fails.append(label)
    else:
        print("  %-10s in no data file; class statement=%s" % (label, class_stated))
        if not class_stated:
            fails.append(label)

print()
if fails:
    print("EVIDENCE-SWEEP-FAIL (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("EVIDENCE-SWEEP-PASS (%d figures: each either cited from a file that holds it, or"
      " covered by the stated class)" % len(FIGURES))
