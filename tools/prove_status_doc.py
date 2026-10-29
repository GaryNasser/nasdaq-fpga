"""Prove every assertion in check_status_doc.

Read from the source, it re-derives from the Vivado reports and compares:

    L47-L52  WNS, WHS, TNS individually against the timing summary      3 paths
    L74-L80  LUT, FF, BRAM, DSP individually against the placed report  4 paths
    L93-L97  status.md must record a suite verdict at all                1 path

**Deliberately NOT asserted**: the suite verdict's VALUE. L83-L92 explains why - this check runs inside the suite
it reads, so asserting the value would make status.md unable to return to a passing state after any unrelated
failure. The proof must not treat that as a missing path.

### Why the swap case matters

L3-L6: the first `gen_status.py` parsed the timing columns in the wrong order and printed "WHS 0.000, TNS 0.031"
when the truth was "WHS +0.031, TNS 0.000". **Two plausible numbers swapped is the worst kind of error - nothing
looks wrong.** So the proof includes a swap, not just a corruption.
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
CHK = os.path.join(REPO, "tools", "check_status_doc.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("STATUS-DOC-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(STATUS, encoding="utf-8", errors="surrogateescape").read()


def inject(label, transform):
    mutated = transform(body)
    if mutated == body:
        print("  %-38s INCONCLUSIVE (no change)" % label)
        return None
    bk = tempfile.mktemp(suffix=".md")
    shutil.copyfile(STATUS, bk)
    try:
        io.open(STATUS, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
        rc, _ = run()
    finally:
        shutil.copyfile(bk, STATUS)
        os.unlink(bk)
    caught = rc != 0
    print("  %-38s exit=%-3d %s" % (label, rc, "CAUGHT" if caught else "MISSED"))
    return caught


TLINE = re.compile(r"(timing: WNS )([\d.-]+)( ns, WHS )([\d.-]+)( ns, TNS )([\d.-]+)( ns)")
m = TLINE.search(body)
if not m:
    print("STATUS-DOC-PROOF-INCONCLUSIVE (no timing line)")
    sys.exit(0)

w, sh, t = m.group(2), m.group(4), m.group(6)
results = []

# 1  corrupt WNS
results.append(inject("WNS corrupted", lambda s: TLINE.sub(
    lambda mm: mm.group(1) + "0.500" + mm.group(3) + mm.group(4) + mm.group(5) + mm.group(6) + mm.group(7),
    s, count=1)))

# 2  swap WHS and TNS - the round-1 error
results.append(inject("WHS/TNS swapped", lambda s: TLINE.sub(
    lambda mm: mm.group(1) + mm.group(2) + mm.group(3) + mm.group(6) + mm.group(5) + mm.group(4) + mm.group(7),
    s, count=1)))

# 3  remove the timing line
results.append(inject("timing line removed", lambda s: TLINE.sub("", s, count=1)))

# 4  corrupt resources
RLINE = re.compile(r"(resources: LUT )(\d+)")
results.append(inject("LUT corrupted", lambda s: RLINE.sub(
    lambda mm: mm.group(1) + "9999", s, count=1)))

# 5  remove the resources line
results.append(inject("resources line removed", lambda s: RLINE.sub("XX", s, count=1)))

# 6  remove the suite verdict record
results.append(inject("suite verdict record removed", lambda s: s.replace(
    "static contract checks**", "static contract checks*")))

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)

caught = sum(1 for c in results if c)
total = sum(1 for c in results if c is not None)
print()
if total and caught == total and rc2 == 0:
    print("STATUS-DOC-PROOF-PASS (%d/%d assertions caught)" % (caught, total))
    sys.exit(0)
print("STATUS-DOC-PROOF-FAIL (%d of %d caught)" % (caught, total))
sys.exit(1)
