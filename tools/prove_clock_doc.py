"""Prove check_clock_doc fails on a stale design-clock claim, and does NOT flag a legitimate
mention of another frequency."""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_clock_doc.py")
TCL = os.path.join(REPO, "vivado", "create_project.tcl")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("CLOCK-DOC-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(TCL, encoding="utf-8", errors="surrogateescape").read()
results = []


def inject(label, transform, expect_fail):
    mutated = transform(body)
    if mutated == body:
        print("  %-46s INCONCLUSIVE" % label)
        return None
    bk = tempfile.mktemp(suffix=".tcl")
    shutil.copyfile(TCL, bk)
    try:
        io.open(TCL, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
        rc, _ = run()
    finally:
        shutil.copyfile(bk, TCL)
        os.unlink(bk)
    failed = rc != 0
    ok = (failed == expect_fail)
    print("  %-46s exit=%-3d %s" % (label, rc,
                                    "as expected" if ok else "*** WRONG ***"))
    return ok


# 1  a stale design-clock claim must FAIL
r1 = inject("design clock claim changed to 210",
            lambda b: b.replace("everything runs at 190 MHz", "everything runs at 210 MHz", 1),
            True)

# 2  a legitimate mention of another frequency must NOT fail
r2 = inject("adds a mention of 200 MHz in an explanation",
            lambda b: b.replace("# PS FCLK_CLK0 at 100 MHz.",
                                "# PS FCLK_CLK0 at 100 MHz; the 200 MHz variant was rejected.", 1),
            False)

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)

oks = [x for x in (r1, r2) if x is not None]
print()
if oks and all(oks) and rc2 == 0:
    print("CLOCK-DOC-PROOF-PASS (a stale claim fails; a legitimate mention does not)")
    sys.exit(0)
print("CLOCK-DOC-PROOF-FAIL")
sys.exit(1)
