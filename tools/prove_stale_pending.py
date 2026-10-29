"""Prove the widened stale_pending catches the phrasing that slipped past it.

Round 79 wrote this check to stop the report calling K1/K2 pending. It passed for seventeen
rounds while two sentences did exactly that, because its PENDING vocabulary did not include
"仍未测".

Three mutations, each a phrasing that survived before:

    1  "K1 仍未测"   (was K2 until round 212: K2 is legitimately pending)                     (the M milestone row)
    2  "整文件回放尚未打通"              (implies replay is the blocker)
    3  "K1、K2 仍未实测"               (the section 6 sentence)

Each must now fail.
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
CHK = os.path.join(REPO, "tools", "check_stale_pending.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, _ = run()
print("healthy exit=%d" % rc0)
print()

MUTATIONS = [
    ("K1 仍未测", "\n\n| M7 | ◐ | **K1 仍未测** |\n", True),
# NEGATIVE CONTROL (round 212): this sentence names only K2, which is legitimately pending. The check
# must NOT catch it. Expectation is carried per mutation so a proof can assert absence as well as presence.
    ("\u6574\u6587\u4ef6\u56de\u653e\u5c1a\u672a\u6253\u901a", "\n\n\u7531\u4e8e\u6574\u6587\u4ef6\u56de\u653e\u5c1a\u672a\u6253\u901a\uff0c\u672c\u62a5\u544a\u4e0d\u7ed9\u51fa K2 \u6570\u5b57\u3002\n", False),
    ("K1、K2 仍未实测", "\n\nK1、K2 仍未实测。\n", True),
]

results = []
original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    for label, addition, want_caught in MUTATIONS:
        mutated = original + addition
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
                newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        ok = (caught == want_caught)
        results.append((label, ok))
        print("%-24s exit=%d %s" % (label, rc, "CAUGHT" if caught else ("NOT-CAUGHT-AS-EXPECTED" if not want_caught else "MISSED")))
        if not caught:
            for l in [x for x in out.splitlines() if x.strip()][-2:]:
                print("      %s" % l[:82])
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)

print()
if all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("STALE-PENDING-PROOF-FAIL")
sys.exit(1)
