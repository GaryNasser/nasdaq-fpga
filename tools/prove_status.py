"""Prove check_status_genuine fails when a live figure in status.md is wrong.

`status.md` claims "every figure was read from an artifact". `check_status_genuine` re-derives each and compares.
**It has never been shown to fail** - and it guards the claim the whole status file rests on.

Mutate one re-derivable figure (the WNS) and confirm exit 1.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
STATUS = os.path.join(REPO, "docs", "status.md")
CHK = os.path.join(REPO, "tools", "check_status_genuine.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

env = {**os.environ, "PATH": r"D:\Xilinx\Vivado\2024.1\bin;" + os.environ.get("PATH", "")}


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), env=env, timeout=900)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, out0 = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("STATUS-PROOF-FAIL (baseline does not pass)")
    for l in [x for x in out0.split("\n") if x.strip()][-3:]:
        print("   " + l.strip()[:80])
    sys.exit(1)

body = io.open(STATUS, encoding="utf-8", errors="surrogateescape").read()

# Find a decimal that the report of record contains, and perturb it.
m = re.search(r"(\d+\.\d{3})\s*ns", body)
if not m:
    m = re.search(r"(\d+\.\d+)", body)
if not m:
    print("STATUS-PROOF-INCONCLUSIVE (no re-derivable figure found in status.md)")
    sys.exit(0)

value = m.group(1)
alt = value[:-1] + ("0" if value[-1] != "0" else "1")
print("exemplar: %s -> %s" % (value, alt))

bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(STATUS, bk)
try:
    io.open(STATUS, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(
        body[:m.start(1)] + alt + body[m.end(1):])
    rc1, out1 = run()
    caught = rc1 != 0
    print("mutated : exit=%d %s" % (rc1, "CAUGHT" if caught else "MISSED"))
    if not caught:
        for l in [x for x in out1.split("\n") if x.strip()][-4:]:
            print("   " + l.strip()[:80])
finally:
    shutil.copyfile(bk, STATUS)
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if caught and rc2 == 0:
    print("STATUS-PROOF-PASS (a wrong live figure in status.md is caught)")
    sys.exit(0)
print("STATUS-PROOF-FAIL (caught=%s restored=%s)" % (caught, rc2 == 0))
sys.exit(1)
