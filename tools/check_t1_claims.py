"""Fix the T1-claim checker: it must read WHICH metric the negation applies to.

The first version flagged the two lines I had just corrected:

    > **板上已实测**：T1 P50 210.5 ns / ... 尚未实测：K1 ...、K2 ...

because the line contains T1, contains 未实测, and my heuristic for "the negation
belongs to another metric" was too weak - it bailed out only when an unrelated
token appeared within 120 characters, which these long lines always satisfy.

The correct rule is positional, not lexical: a negation applies to the metric
spelled closest BEFORE it on the same line. So find each negation, look backwards
for the nearest metric name, and only complain when that name is T1.

This is the fourth checker in this arc that had to be fixed rather than the
artifact. The recurring shape: the check encodes a shortcut (same line = same
subject) that happens to hold for the examples I had in mind, then fails on the
corrected text.
"""
import io
import os
import re
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = r"D:\agent\nasdaq-fpga"
DOCS = ["docs/final-report.md", "docs/status.md"]

NEG = re.compile(r"(未实测|尚未实测|not measured|unmeasured|未采到|no samples)",
                 re.I)
# Every metric name that can be the subject of a negation.
METRIC = re.compile(r"(T1|延迟分布|K1|K2|DMA|吞吐|throughput|percentile|P50|P95|P99)",
                    re.I)


def subject_before(line, pos):
    """The metric named closest before `pos` on this line, if any."""
    best = None
    for m in METRIC.finditer(line, 0, pos):
        best = m.group(1)
    return best


fails = []
scanned = 0
print("scanning for claims that board T1 is unmeasured")

for rel in DOCS:
    path = os.path.join(REPO, rel)
    if not os.path.exists(path):
        continue
    text = io.open(path, encoding="utf-8", errors="surrogateescape").read()
    for n, line in enumerate(text.split("\n"), 1):
        scanned += 1
        # A markdown table row whose first cell is a backticked identifier is a
        # description OF a check, not a claim in the report. Without this, the row
        # `| t1_claims | 没有文档仍称板上 T1 未实测 |` reads as the very defect the
        # check looks for.
        if re.match(r"\|\s*`\w+`\s*\|", line.strip()):
            continue
        for m in NEG.finditer(line):
            subj = subject_before(line, m.start())
            # "延迟分布" is T1 under another name; so are the percentile labels.
            is_t1 = bool(subj) and (
                subj.upper().startswith("T1")
                or "延迟分布" in subj
                or subj.lower() in ("percentile", "p50", "p95", "p99",
                                    "latency distribution"))
            if is_t1:
                fails.append((rel, n, line.strip()[:110]))
                print("  %s:%d T1 is the subject of an unmeasured claim" % (rel, n))
                break

print()
print("scanned %d line(s) in %d file(s)" % (scanned, len(DOCS)))
if fails:
    print("T1-CLAIM-FAIL (%d)" % len(fails))
    for rel, n, txt in fails:
        print("  %s:%d  %s" % (rel, n, txt))
    sys.exit(1)
print("T1-CLAIM-PASS")
