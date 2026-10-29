"""Prove check_board_offline catches a check that reports a defect when the board is absent.

Round 23: prove_pair_guard treated BOARD-UNREACHABLE as "the control does not pass". This restores that reading and
requires the offline sweep to see it.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
TARGET = os.path.join(TOOLS, "prove_pair_guard.py")
SWEEP = os.path.join(TOOLS, "check_board_offline.py")


def run():
    r = subprocess.run([sys.executable, SWEEP], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS, timeout=1800)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# Round 31: this proof can only exercise the offline path while the board IS offline. With the board
# online, prove_pair_guard never takes that branch, so removing it changes nothing and the mutation
# cannot land. Say so instead of reporting the guard as broken.
import socket

_board_up = False
try:
    _sock = socket.create_connection(("100.113.173.88", 22), timeout=6)
    _sock.close()
    _board_up = True
except OSError:
    pass

if _board_up:
    print("board is ONLINE - the offline guard is unreachable, so this proof cannot run")
    rc0, out0 = run()
    print("control : exit=%d  %s" % (rc0, "BOARD-OFFLINE-PASS" if "BOARD-OFFLINE-PASS" in out0 else "?"))
    print()
    print("BOARD-OFFLINE-PROOF-INCONCLUSIVE (the condition it tests for is absent)")
    print("  The guard itself is not in question; re-run this proof with the board powered down.")
    import sys as _sys
    _sys.exit(0)

rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "BOARD-OFFLINE-PASS" if "BOARD-OFFLINE-PASS" in out0 else "?"))
if rc0 != 0:
    print("BOARD-OFFLINE-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(TARGET, encoding="utf-8").read()
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(TARGET, bk)
st = os.stat(TARGET)
try:
    # Remove the round-23 guard so an absent board is reported as a failure again.
    cut = orig.find("if rc == 2 and \"BOARD-UNREACHABLE\" in out:")
    end = orig.find("if rc != 0:", cut)
    landed = cut > 0 and end > cut
    mutated = orig[:cut] + orig[end:] if landed else orig
    io.open(TARGET, "w", encoding="utf-8", newline="\n").write(mutated)
    rc1, out1 = run()
    caught = rc1 != 0 and "BOARD-OFFLINE-FAIL" in out1
    print("remove the offline guard   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
    if landed and not caught:
        for l in out1.split("\n"):
            if "pair_guard_proof" in l:
                print("   " + l.strip()[:80])
finally:
    shutil.copyfile(bk, TARGET)
    os.utime(TARGET, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("BOARD-OFFLINE-PROOF-PASS (an absent board read as a defect is caught)")
    sys.exit(0)
print("BOARD-OFFLINE-PROOF-FAIL")
sys.exit(1)
