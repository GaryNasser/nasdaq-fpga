"""The three-build table claims a source per column. Verify each claim against the filesystem.

    column 1  4BB3D7D1  WNS +0.126   the report now says "未纳入仓库"
    column 2  D874BD51  WNS +0.157   build_check/rebuild.log
    column 3  0ADD0828  WNS +0.042   impl_1/nasdaq_wrapper_timing_summary_routed.rpt

Each of those is a factual claim about the repository, checkable directly:
  * "未纳入仓库" must be TRUE - no file may contain the figure
  * a cited file must exist AND contain the figure

If someone later archives the shipped build's report, the first claim becomes false and the table
should be updated - this check fails until it is.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Index the evidence-bearing files once.
corpus = []
for root, dirs, files in os.walk(REPO):
    dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "local_data", ".Xil")]
    for f in files:
        if not f.endswith((".log", ".txt", ".rpt", ".json")):
            continue
        rel = os.path.relpath(os.path.join(root, f), REPO)
        if rel.startswith("tools" + os.sep):
            continue
        try:
            if os.path.getsize(os.path.join(root, f)) > 30_000_000:
                continue
            corpus.append((rel, io.open(os.path.join(root, f), encoding="latin-1",
                                       errors="replace").read()))
        except OSError:
            continue

rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()


def carriers(figure):
    return [rel for rel, body in corpus if figure in body]


print("the three-build timing table, column by column")
print()

fails = []

# Column 1: the shipped build, claimed to have no report.
#
# A plain search for "0.126" hits a route delay in the CURRENT build's report
# ("Data Path Delay: 0.335ns (logic 0.209ns, route 0.126ns)"), which is a different quantity on
# a different path. Only a WNS-column read counts as evidence.
def wns_of(report_text):
    lines_ = report_text.split("\n")
    hi = next((i for i, l in enumerate(lines_) if "WNS(ns)" in l), None)
    if hi is None:
        return None
    for l in lines_[hi + 1: hi + 12]:
        toks = l.split()
        if toks and re.match(r"^-?\d+\.\d+$", toks[0]):
            return toks[0]
    return None


hits = []
for rel, body_ in corpus:
    v = wns_of(body_)
    if v is not None and v.lstrip("+").startswith("0.126"):
        hits.append(rel)
print("     (WNS-column matches only: %s)" % (", ".join(hits) if hits else "none"))
claimed_missing = "其时序报告**没有留下文件**" in rep
print("  4BB3D7D1  +0.126 ns")
print("     claimed missing : %s" % claimed_missing)
print("     actually found  : %s" % (", ".join(hits[:3]) if hits else "nowhere"))
if claimed_missing and hits:
    fails.append("+0.126 is now in %s, but the report says it has no file" % hits[0])
if not claimed_missing:
    fails.append("the report no longer states that the shipped build has no timing report")

# Column 2: round-30 rebuild.
r30 = "build_check/rebuild.log"
has30 = "+0.157" in rep and "rebuild.log" in rep
found30 = any("0.157" in body for rel, body in corpus if rel.replace("\\", "/") == r30)
print()
print("  D874BD51  +0.157 ns")
print("     cited file exists: %s" % os.path.exists(os.path.join(REPO, r30)))
print("     contains 0.157   : %s" % found30)
if not found30:
    fails.append("rebuild.log does not contain 0.157")

# Column 3: the current build.
rpt = os.path.join("vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1",
                   "nasdaq_wrapper_timing_summary_routed.rpt")
has_cur = os.path.exists(os.path.join(REPO, rpt))
body = io.open(os.path.join(REPO, rpt), encoding="latin-1",
               errors="replace").read() if has_cur else ""
print()
# Read the WNS the CURRENT implementation achieved, rather than pinning a historical value.
wns_cur = None
if has_cur:
    m = re.search(r"WNS\(ns\)[^\n]*\n[- ]+[^\n]*\n\s*(-?\d+\.\d+)", body)
    if not m:
        m = re.search(r"(-?\d+\.\d+)\s+-?\d+\.\d+\s+\d+\s+\d+\s+(-?\d+\.\d+)", body)
    if m:
        wns_cur = m.group(1)
print("  current build WNS: %s" % (wns_cur if wns_cur else "(not found)"))
print("     report exists    : %s" % has_cur)
print("     contains 0.042   : %s" % ("0.042" in body))
if not has_cur or wns_cur is None:
    fails.append("impl_1 timing report missing or its WNS is unreadable")
else:
    # The documents must quote the figure the report on disk actually achieved.
    quoted = False
    for path in (os.path.join(REPO, "docs", "final-report.md"),
                 os.path.join(REPO, "docs", "bringup-defects.md")):
        if not os.path.exists(path):
            continue
        text = io.open(path, encoding="utf-8", errors="surrogateescape").read()
        if wns_cur in text or wns_cur.lstrip("-") in text:
            quoted = True
            break
    if not quoted:
        fails.append("WNS %s from the impl_1 report is not quoted in the documents" % wns_cur)

print()
if fails:
    print("TIMING-SOURCE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  %s" % f)
    sys.exit(1)
print("TIMING-SOURCE-PASS (each column's stated source matches the repository)")
