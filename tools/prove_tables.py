"""Verify audit_tables would catch a table figure that changed in one copy but not the other.

There are two copies of the timing table (L193 and L425) with identical values. **Change one and the audit must
fail** - that is the whole point of comparing them.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
TOOLS = os.path.join(REPO, "tools")
CHK = os.path.join(TOOLS, "audit_tables.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=TOOLS, timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, out0 = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("TABLE-AUDIT-PROOF-FAIL (baseline does not run)")
    for l in [x for x in out0.split("\n") if x.strip()][:3]:
        print("   " + l.strip()[:80])
    sys.exit(1)

bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    lines = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read().split("\n")
    # Change ONLY the second copy's WNS row (around L429).
    hit = 0
    for i, l in enumerate(lines):
        if l.strip().startswith("| WNS |") and "+0.094 ns**" in l:
            hit += 1
            if hit == 2:
                lines[i] = l.replace("+0.094 ns", "+0.099 ns")
                print("mutated L%d: one copy now says +0.099 ns" % (i + 1))
                break
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write("\n".join(lines))

    rc1, out1 = run()
    caught = rc1 != 0
    print("mutated : exit=%d %s" % (rc1, "CAUGHT" if caught else "MISSED"))
    if not caught:
        for l in [x for x in out1.split("\n") if x.strip()][:4]:
            print("   " + l.strip()[:80])
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if caught and rc2 == 0:
    print("TABLE-AUDIT-PROOF-PASS (a table figure changed in one copy is caught)")
    sys.exit(0)
print("TABLE-AUDIT-PROOF-FAIL")
sys.exit(1)
