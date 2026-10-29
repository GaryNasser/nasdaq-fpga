"""Prove check_timing_source fails on the two ways the table can go wrong.

    1  the report stops stating that the shipped build has no timing report
       (a reader would assume all three columns are traceable)
    2  rebuild.log stops containing 0.157 (the cited file no longer supports its column)

Both must fail.
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
REBUILD = os.path.join(REPO, "build_check", "rebuild.log")
CHK = os.path.join(REPO, "tools", "check_timing_source.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


results = []

# 1. Remove the "no file" statement.
rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
OLD = "其时序报告**没有留下文件**"
if OLD in rep:
    bk = tempfile.mktemp(suffix=".md")
    shutil.copyfile(REPORT, bk)
    try:
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
                newline="\n").write(rep.replace(OLD, "其时序报告见 impl_1", 1))
        rc, out = run()
        caught = rc != 0
        results.append(("gap statement removed", caught))
        print("%-32s exit=%d %s" % ("gap statement removed", rc,
                                    "CAUGHT" if caught else "MISSED"))
    finally:
        shutil.copyfile(bk, REPORT)
        os.unlink(bk)
else:
    print("%-32s NOT APPLIED" % "gap statement removed")

# 2. rebuild.log loses 0.157.
if os.path.exists(REBUILD):
    body = io.open(REBUILD, encoding="latin-1", errors="replace").read()
    if "0.157" in body:
        bk = tempfile.mktemp(suffix=".log")
        shutil.copyfile(REBUILD, bk)
        try:
            io.open(REBUILD, "w", encoding="latin-1", errors="replace",
                    newline="\n").write(body.replace("0.157", "0.999"))
            rc, out = run()
            caught = rc != 0
            results.append(("rebuild.log loses 0.157", caught))
            print("%-32s exit=%d %s" % ("rebuild.log loses 0.157", rc,
                                        "CAUGHT" if caught else "MISSED"))
        finally:
            shutil.copyfile(bk, REBUILD)
            os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("TIMING-SOURCE-PROOF-FAIL")
sys.exit(1)
