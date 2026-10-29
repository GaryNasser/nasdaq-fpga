"""Make check_module_idle_reach report a stuck state, proving its "19 of 19" responds to RTL.

Four earlier attempts failed, each by acting on a guess:

    default -> current state          every arm has its own transition; nothing changed
    ST_EMIT's arm via plain regex     the first "ST_EMIT:" is inside a COMMENT; the "arm" was
                                      13,690 characters of unrelated text
    ST_EMIT again, comments stripped  its arm contains zero `state <=` assignments
    (enumeration)                     -> ST_SESSION0: 342 chars, exactly one successor

The mutation that lands: rewrite ST_SESSION0's `state <= ST_SESSION1` to `state <= ST_SESSION0`.
ST_SESSION1..7 then become unreachable from ST_IDLE.

Expected: "18 reach ST_IDLE, 1 stuck" and a non-zero exit naming ST_SESSION0.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch", "mold64_reasm.v")
CHK = os.path.join(REPO, "tools", "check_module_idle_reach.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


src = io.open(RTL, encoding="latin-1").read()
# Blank comments while preserving offsets, so positions map back exactly.
blanked = re.sub(r"//[^\n]*", lambda m: " " * len(m.group(0)), src)
blanked = re.sub(r"/\*.*?\*/",
                 lambda m: re.sub(r"[^\n]", " ", m.group(0)), blanked, flags=re.S)

mc = re.search(r"case\s*\(\s*state\s*\)", blanked)
if not mc:
    print("REACH-RESPONDS-FAIL (no case(state))")
    sys.exit(1)

arm = re.search(r"\bST_SESSION0\s*:", blanked[mc.end():])
if not arm:
    print("REACH-RESPONDS-FAIL (no ST_SESSION0 arm)")
    sys.exit(1)
a = mc.end() + arm.end()
nxt = re.search(r"\n\s*ST_[A-Z0-9_]+\s*:", blanked[a:])
if not nxt:
    print("REACH-RESPONDS-FAIL (no following arm)")
    sys.exit(1)
b = a + nxt.start()

segment = src[a:b]
mutated_seg = re.sub(r"state\s*<=\s*ST_SESSION1", "state <= ST_SESSION0", segment)
if mutated_seg == segment:
    print("REACH-RESPONDS-FAIL (ST_SESSION1 assignment not found in the arm)")
    sys.exit(1)

mutated = src[:a] + mutated_seg + src[b:]
print("ST_SESSION0: state <= ST_SESSION1  ->  state <= ST_SESSION0")

bk = tempfile.mktemp(suffix=".v")
shutil.copyfile(RTL, bk)
try:
    io.open(RTL, "w", encoding="latin-1", newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    for l in out.splitlines():
        if "mold64_reasm" in l or "FAIL" in l:
            print("   %s" % l.strip()[:86])
    print("   exit=%d %s" % (rc, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, RTL)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)

if caught and rc2 == 0:
    sys.exit(0)
print("REACH-RESPONDS-FAIL")
sys.exit(1)
