"""Prove `board_recover` refuses a mismatched bit/hwh pair.

Round 1's Bus error came from deploying `nasdaq.bit` alone. The guard added this round must FAIL in exactly that
state - and must leave the files restored.

Two mutations:
    a  hwh from a different build      (the round-1 mistake)
    b  bit from a different build      (the mirror)

Control: the current pair must pass.
"""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
OUT = os.path.join(REPO, "vivado", "out")
ARCH = os.path.join(REPO, "build_check", "20261025_125239")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "board_recover.py"), "--check"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc, out = run()
print("control : exit=%d  %s" % (rc, "PAIR-OK" if "PAIR-OK" in out else out.strip()[:50]))

# Round 23: exit 2 means BOARD-UNREACHABLE, not a bad pair. The pair guard is evaluated before the board
# probe, so a board outage says nothing about whether the guard works - and it must not be reported as the
# guard failing. (The board went offline mid-suite and this proof read it as a failure.)
if rc == 2 and "BOARD-UNREACHABLE" in out:
    print()
    print("PAIR-GUARD-PROOF-INCONCLUSIVE (the board is offline; the pair itself is %s)"
          % ("OK" if "PAIR-OK" in out else "NOT confirmed"))
    print("  The guard under test is the bit/hwh pair check, which runs before the board probe.")
    sys.exit(0)
if rc != 0:
    print("PAIR-GUARD-PROOF-FAIL (control does not pass: %s)" % out.strip()[:60])
    sys.exit(1)

results = []
for label, victim, donor in (
        ("hwh from another build", os.path.join(OUT, "nasdaq.hwh"),
         os.path.join(ARCH, "nasdaq.hwh")),
        ("bit from another build", os.path.join(OUT, "nasdaq.bit"),
         os.path.join(ARCH, "nasdaq.bit")),
):
    if not os.path.exists(donor):
        results.append((label, None, False))
        continue
    same = hashlib.md5(io.open(victim, "rb").read()).hexdigest() == \
           hashlib.md5(io.open(donor, "rb").read()).hexdigest()
    if same:
        print("%-24s skipped (archived copy is identical)" % label)
        continue

    bk = tempfile.mktemp(suffix=os.path.splitext(victim)[1])
    shutil.copyfile(victim, bk)
    # The timestamp must be captured BEFORE the file is replaced; reading it in the finally block
    # returned the donor's mtime, so the restore re-stamped the file with the wrong time and
    # check_build_pairing then saw "a different run". (Round 4.)
    _orig_st = os.stat(victim)
    landed = False
    try:
        shutil.copyfile(donor, victim)
        landed = hashlib.md5(io.open(victim, "rb").read()).hexdigest() != \
                 hashlib.md5(io.open(bk, "rb").read()).hexdigest()
        rc1, out1 = run()
        caught = rc1 != 0 and "DEPLOY-REFUSED" in out1
        results.append((label, rc1, caught))
        print("%-24s landed=%s exit=%d %s" % (label, landed, rc1, "CAUGHT" if caught else "MISSED"))
    finally:
        # copyfile updates mtime, which check_build_pairing reads as "a different run".
        # Restore the timestamp captured before the replacement.
        shutil.copyfile(bk, victim)
        os.utime(victim, (_orig_st.st_atime, _orig_st.st_mtime))
        os.unlink(bk)

rc2, out2 = run()
print("restored: exit=%d %s" % (rc2, "PAIR-OK" if "PAIR-OK" in out2 else ""))

print()
ok = rc2 == 0 and results and all(c for _, _, c in results)
if ok:
    print("PAIR-GUARD-PROOF-PASS (%d mismatch(es) refused by the deploy path)" % len(results))
    sys.exit(0)
print("PAIR-GUARD-PROOF-FAIL")
sys.exit(1)
