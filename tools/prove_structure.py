"""Prove each newly added structure mode is actually caught.

Four injections, each breaking one mode, each of which must make check_report_structure fail:

    unbalanced code fence
    heading level skip
    duplicate heading text
    link to a file that does not exist

Then restore and confirm it passes. **A mode that is claimed but not proven is the round-222 mistake again.**
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHK = os.path.join(REPO, "tools", "check_report_structure.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FENCE = "`" * 3


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, out0 = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("STRUCTURE-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

CASES = [
    ("unbalanced fence", "\n\n" + FENCE + "\nsome code\n"),
    ("heading skip", "\n\n##### orphan level five\n"),
    ("duplicate heading", "\n\n## 1. \u5e73\u53f0\u4e0e\u76ee\u6807\u91cd\u951a\u5b9a\n"),
    ("broken link", "\n\n\u53c2\u89c1 [\u4e0d\u5b58\u5728\u7684\u6587\u4ef6](docs/no-such-file.md)\u3002\n"),
]

results = []
for label, injection in CASES:
    bk = tempfile.mktemp(suffix=".md")
    shutil.copyfile(REPORT, bk)
    try:
        body = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(body + injection)
        rc, out = run()
    finally:
        shutil.copyfile(bk, REPORT)
        os.unlink(bk)
    caught = rc != 0
    results.append((label, caught))
    print("  %-20s exit=%-3d %s" % (label, rc, "CAUGHT" if caught else "MISSED"))

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)

caught_n = sum(1 for _, c in results if c)
print()
if caught_n == len(results) and rc2 == 0:
    print("STRUCTURE-PROOF-PASS (%d/%d modes caught)" % (caught_n, len(results)))
    sys.exit(0)
print("STRUCTURE-PROOF-FAIL (%d of %d caught)" % (caught_n, len(results)))
for label, c in results:
    if not c:
        print("   missed: " + label)
sys.exit(1)
