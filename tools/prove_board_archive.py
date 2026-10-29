"""Prove check_board_archive fails when a board-facing tool neither archives nor explains why not.

Round 192 built this check: every script that talks to the board must import `board_archive`, write to
`docs/measurements/`, or be listed in EXEMPT with a reason. **It has never been shown to fail.**

Inject a script that names `ssh` and does neither.
"""
import io
import os
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_board_archive.py")
FAKE = os.path.join(REPO, "tools", "zz_ssh_no_archive.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, out0 = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("BOARD-ARCHIVE-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

FAKE_BODY = '''"""A board-facing tool that records nothing and is not exempt."""
import subprocess
import sys

BOARD = "pynq-z2-codex"
r = subprocess.run(["ssh", BOARD, "echo hi"], capture_output=True)
print((r.stdout or b"").decode())
sys.exit(0)
'''

io.open(FAKE, "w", encoding="utf-8", newline="\n").write(FAKE_BODY)
try:
    rc1, out1 = run()
    caught = rc1 != 0
    named = "zz_ssh_no_archive" in out1
    print("injected zz_ssh_no_archive.py")
    print("mutated : exit=%d %s%s" % (rc1, "CAUGHT" if caught else "MISSED",
                                      "" if named else "  (but does not name it)"))
    if not caught:
        for l in [x for x in out1.split("\n") if x.strip()][-4:]:
            print("   " + l.strip()[:80])
finally:
    os.unlink(FAKE)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if caught and named and rc2 == 0:
    print("BOARD-ARCHIVE-PROOF-PASS (an unarchived board tool is caught and named)")
    sys.exit(0)
print("BOARD-ARCHIVE-PROOF-FAIL (caught=%s named=%s restored=%s)" % (caught, named, rc2 == 0))
sys.exit(1)
