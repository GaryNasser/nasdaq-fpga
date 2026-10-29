"""deliverables exits 75 when every gap is PENDING and 1 when one is "broken".

The check parses audit_deliverables' output, splits the gaps into PENDING (hardware supports
them, board offline) and broken (everything else), and fails only on broken ones.

To prove it can fail, I need a gap that is neither. The cleanest: make the audit report an
item as NOT DONE for a reason outside PENDING - e.g. by hiding a file the audit needs for a
deliverable that is currently present.

The audit reads data/itch_loc6836.mold64 for pack_count(). Hiding it turns
"reassembler 850 packets" and "parser 43428 messages" into gaps with the text "tb_fullchain
+ 板级回放" and "tb_fullchain" - neither of which is in PENDING, so check_deliverables must
exit 1.

That also exercises the audit's own honesty: a missing capture should make it say so.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
DATA = os.path.join(REPO, "data", "itch_loc6836.mold64")
CHK = os.path.join(TOOLS, "check_deliverables.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("baseline exit=%d" % rc0)
for l in out0.splitlines()[-3:]:
    if l.strip():
        print("   %s" % l.strip()[:84])
print()

if not os.path.exists(DATA):
    print("DELIVERABLE-PROOF-FAIL (capture already missing)")
    sys.exit(1)

hidden = DATA + ".hidden"
os.rename(DATA, hidden)
try:
    rc, out = run()
    caught = rc == 1
    print("with data/itch_loc6836.mold64 hidden:")
    for l in out.splitlines()[-8:]:
        if l.strip():
            print("   %s" % l.strip()[:86])
    print("   exit=%d %s" % (rc, "CAUGHT (exit 1)" if caught else "MISSED"))
finally:
    os.rename(hidden, DATA)

rc2, out2 = run()
print()
print("restored exit=%d" % rc2)

if caught and rc2 == 75:
    sys.exit(0)
if caught and rc2 in (0, 75):
    sys.exit(0)
print("DELIVERABLE-PROOF-FAIL")
sys.exit(1)
