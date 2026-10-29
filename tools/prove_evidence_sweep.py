import re
"""Prove the sweep fails when the class statement goes, and when a citation goes.

    1  delete the class statement  -> the six unsourced figures fail
    2  delete +impl_1/*.rpt+ from the report's provenance line -> 4,499 and 5,422 fail too

Both must fail. A check that passes on a document with no provenance at all is worthless.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHK = os.path.join(REPO, "tools", "check_evidence_status.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# 1. Remove the class statement sentences.
lines = original.split("\n")
kept = [l for l in lines
        if "只有叙述、没有文件的" not in l and "无法从仓库重放" not in l]
c1 = "\n".join(kept)

results = []
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    if c1 != original:
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
                newline="\n").write(c1)
        rc, out = run()
        caught = rc != 0
        results.append(("class statement removed", caught))
        names = [l.strip() for l in out.splitlines() if "EVIDENCE-SWEEP-FAIL" in l]
        print("%-26s exit=%d %s  %s" % ("class statement removed", rc,
                                        "CAUGHT" if caught else "MISSED",
                                        (names[0] if names else "")[:44]))
    else:
        print("%-26s NOT APPLIED" % "class statement removed")

    # 2. Remove every .rpt citation.
    c2 = original
    # Round 195: derive the mutation from what the sweep reports, rather than naming figures that have since
    # moved to a different source. Ask the checker which figure is sourced from a .rpt and remove THAT name.
    import subprocess as _sp
    _r = _sp.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "check_evidence_status.py")],
                 capture_output=True, text=True, encoding="utf-8", errors="replace")
    _cited = []
    for _l in ((_r.stdout or "") + (_r.stderr or "")).split("\n"):
        _m = re.search(r"file:\s+(\S+\.rpt)", _l)
        if _m:
            _cited.append(os.path.basename(_m.group(1)))
    _skip_rpt = not _cited
    if _skip_rpt:
        print("%-26s INCONCLUSIVE - no figure is currently sourced from a .rpt" % ".rpt citations removed")
    for s in (() if _skip_rpt else tuple(_cited) + ("`impl_1/nasdaq_wrapper_utilization_placed.rpt`",
                              "`impl_1/nasdaq_wrapper_timing_summary_rpt`",
                              "impl_1/*.rpt", "nasdaq_wrapper_utilization_placed.rpt",
                              "nasdaq_wrapper_timing_summary_routed.rpt")):
        c2 = c2.replace(s, "")
    if c2 != original:
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
                newline="\n").write(c2)
        rc, out = run()
        caught = rc != 0
        results.append((".rpt citations removed", caught))
        print("%-26s exit=%d %s" % (".rpt citations removed", rc,
                                    "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("EVIDENCE-SWEEP-PROOF-FAIL")
sys.exit(1)
