"""Prove check_fsm_states catches an unreachable and an unexitable state."""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_fsm_states.py")
RTL = os.path.join(REPO, "rtl", "itch", "mold64_reasm.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("FSM-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

CASES = [
    ("state assigned but never tested or cased",
     "  localparam [4:0] ST_ORPHAN = 5'd31;\n", None),
    ("state tested but never assigned",
     None, "  else if (state == ST_GHOST) begin end\n"),
]

results = []
for label, decl, use in CASES:
    bk = tempfile.mktemp(suffix=".v")
    shutil.copyfile(RTL, bk)
    try:
        src = io.open(RTL, encoding="latin-1").read()
        if decl:
            src = src.replace("  localparam [4:0] ST_IDLE", decl + "  localparam [4:0] ST_IDLE", 1)
            # Also assign it so it has an entry.
            src = src.replace("state         <= ST_SESSION0;", "state <= ST_ORPHAN;", 1)
        if use:
            src = src.replace("  localparam [4:0] ST_IDLE",
                              "  localparam [4:0] ST_GHOST = 5'd30;\n  localparam [4:0] ST_IDLE", 1)
            src = src.replace("if (state == ST_IDLE && fifo_not_empty_live",
                              "if (state == ST_GHOST) begin end\n      else if (state == ST_IDLE && fifo_not_empty_live", 1)
        io.open(RTL, "w", encoding="latin-1", newline="\n").write(src)
        rc, out = run()
    finally:
        shutil.copyfile(bk, RTL)
        os.unlink(bk)
    caught = rc != 0
    results.append((label, caught))
    print("  %-40s exit=%-3d %s" % (label, rc, "CAUGHT" if caught else "MISSED"))

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)

caught_n = sum(1 for _, c in results if c)
print()
if caught_n == len(results) and rc2 == 0:
    print("FSM-PROOF-PASS (%d/%d caught)" % (caught_n, len(results)))
    sys.exit(0)
print("FSM-PROOF-FAIL (%d of %d caught)" % (caught_n, len(results)))
sys.exit(1)
