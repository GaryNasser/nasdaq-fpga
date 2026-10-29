"""Prove check_repro_args fails when a required argument is dropped from the report.

Mutation: revert gen_itch_tv.py's line to the bare form that shipped for many rounds.
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
CHK = os.path.join(REPO, "tools", "check_repro_args.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
m = re.search(r"python tools/gen_itch_tv\.py[^\n]*", rep)
if not m:
    print("REPRO-ARGS-PROOF-FAIL (command not found)")
    sys.exit(1)

mutated = rep[:m.start()] + "python tools/gen_itch_tv.py" + rep[m.end():]

results = []
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    results.append(("drop --input/--out-dir", caught))
    detail = next((l.strip() for l in out.splitlines() if "requires" in l and "supplies" in l), "")
    print("%-24s exit=%d %s  %s" % ("drop --input/--out-dir", rc,
                                    "CAUGHT" if caught else "MISSED", detail[:44]))
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("REPRO-ARGS-PROOF-FAIL")
sys.exit(1)
