"""Keep the proofs: artifacts and module_ff were verified with a script I then deleted.

The pattern has now cost three rounds:

    84  bit_repro / provenance_current proven with a scratch file, deleted -> unproven
    90  artifacts / module_ff proven with prove_four.py, deleted          -> unproven

Each time the ledger correctly reports them unproven, because a deleted script is not a
harness. The ledger is right; the habit is wrong.

This is the permanent version, kept in tools/ and registered in the suite. Two mutations:

    artifacts    hide the .hwh  -> check_artifacts must fail
    module_ff    edit a per-module count in the report -> must fail
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
OUT = os.path.join(REPO, "vivado", "out")
HWH = os.path.join(OUT, "nasdaq.hwh")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run(check):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, check)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


results = []

# 1. artifacts: the handoff file disappears.
if os.path.exists(HWH):
    hidden = HWH + ".hidden"
    os.rename(HWH, hidden)
    try:
        rc, out = run("check_artifacts.py")
        caught = rc != 0
        results.append(("artifacts: .hwh absent", caught))
        print("%-34s exit=%d %s" % ("artifacts: .hwh absent", rc,
                                    "CAUGHT" if caught else "MISSED"))
    finally:
        os.rename(hidden, HWH)
else:
    print("%-34s SKIPPED (no .hwh)" % "artifacts")

# 2. module_ff: a per-module count in the report.
rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
m = re.search(r"order_book\s*=\s*(\d+)", rep)
if m:
    mutated = rep[:m.start(1)] + str(int(m.group(1)) + 7) + rep[m.end(1):]
    bk = tempfile.mktemp(suffix=".md")
    shutil.copyfile(REPORT, bk)
    try:
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
                newline="\n").write(mutated)
        rc, out = run("check_module_ff.py")
        caught = rc != 0
        results.append(("module_ff: count +7", caught))
        print("%-34s exit=%d %s" % ("module_ff: count +7", rc,
                                    "CAUGHT" if caught else "MISSED"))
        if not caught:
            for l in [x for x in out.splitlines() if x.strip()][-2:]:
                print("      %s" % l[:80])
    finally:
        shutil.copyfile(bk, REPORT)
        os.unlink(bk)
else:
    print("%-34s SKIPPED (pattern not found)" % "module_ff")

# Healthy path.
ok_restore = True
for c in ("check_artifacts.py", "check_module_ff.py"):
    rc, _ = run(c)
    if rc != 0:
        ok_restore = False
    print("  %-30s exit=%d (restored)" % (c, rc))

print()
if results and all(c for _, c in results) and ok_restore:
    sys.exit(0)
print("ARTIFACT-FF-PROOF-FAIL")
sys.exit(1)
