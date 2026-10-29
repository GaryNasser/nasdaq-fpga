"""The negation override must not make the check blind again.

After the fix it passes on L1201 (a denial - correct). The question is whether it still fails on
a genuine deferral. Plants, in the report's own form:

    "K1 仍未测。"               - the exact phrasing that was silent before this round
    "K2 尚未实测。"             - another form
    "DMA→DDR 待补充。"          - the original vocabulary

And a control that must NOT fail:

    "K1 不是「尚未做」，而是硬件不可行。"   - a denial, correct
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHK = os.path.join(REPO, "tools", "check_impossible_stated.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode


original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)

CASES = [
    ("K1 仍未测。", True),
    ("K2 尚未实测。", True),
    ("DMA→DDR 待补充。", True),
    ("K1 不是「尚未做」，而是硬件不可行。", False),
]

results = []
try:
    for sentence, should_fail in CASES:
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
                newline="\n").write(original + "\n\n" + sentence + "\n")
        rc = run()
        failed = rc != 0
        ok = failed == should_fail
        results.append((sentence, should_fail, failed, ok))
        print("%-42s expected %-7s got %-7s %s"
              % (sentence[:42], "FAIL" if should_fail else "pass",
                 "FAIL" if failed else "pass", "ok" if ok else "WRONG"))
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

print()
print("restored exit=%d" % run())

print()
if all(r[3] for r in results):
    sys.exit(0)
print("NEGATION-PROOF-FAIL")
sys.exit(1)
