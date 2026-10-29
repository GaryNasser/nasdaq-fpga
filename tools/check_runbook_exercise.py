"""Accepting a flag is not the same as running correctly.

`chunk_sweep.py --input data/itch_1m.mold64 --run` parses fine, and would then try to SSH to
a board that is offline. `board_recover.py --check` parses fine and exits 2.

So "the command exists" is necessary but not sufficient. What can be verified without a
board is that each documented command fails in the way the runbook says it does.

For each cited command, the runbook states an expected outcome:

    board_recover.py --check     reachable -> exit 0 ; unreachable -> exit 2
    board_recover.py             exit codes 0,2,3,4,5,6 documented
    chunk_sweep.py --run         needs a board; without one it must fail, not hang
    run_checks.py                exit 0 with SUITE-PASS
    run_sims.py                  exit 0 with SIMSUITE-PASS

Two of those five can be exercised now. This runs them and compares against the stated
expectation, so the document's promises are tested rather than asserted.
"""
import io
import os
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

env = dict(os.environ)
env["PATH"] = r"D:\Xilinx\Vivado\2024.1\bin;" + env.get("PATH", "")
env["PYTHONIOENCODING"] = "utf-8"

print("documented commands, exercised against the current board")
print()
fails = []

# 1. board_recover --check must exit 2 while the board is down, with a clear message.
r = subprocess.run([sys.executable, os.path.join(REPO, "tools", "board_recover.py"),
                    "--check"], capture_output=True, text=True, encoding="utf-8",
                   errors="replace", env=env, timeout=120)
out = (r.stdout or "") + (r.stderr or "")
unreachable = "BOARD-UNREACHABLE" in out
reachable = "board reachable" in out
# The runbook documents both outcomes: exit 2 with BOARD-UNREACHABLE when the board is down, and
# exit 0 when it is up. Pinning this to the offline case made the check fail the moment the board
# came back - which is not a defect in the tool.
if reachable:
    code_ok = r.returncode == 0
    expected = "0 (board reachable)"
else:
    code_ok = r.returncode == 2
    expected = "2 (unreachable)"
print("  board_recover.py --check")
print("     exit %d, runbook documents %s  %s"
      % (r.returncode, expected, "ok" if code_ok else "MISMATCH"))
print("     board reachable: %s   prints BOARD-UNREACHABLE: %s" % (reachable, unreachable))
if not code_ok:
    fails.append("board_recover --check exits %d, expected %s" % (r.returncode, expected))
if not (reachable or unreachable):
    fails.append("board_recover --check prints neither the reachable nor the unreachable token")

# 2. chunk_sweep must refuse cleanly without a board rather than hang.
#
# It must NOT run the sweep when the board IS up: this is a check, and each live sweep
# takes minutes and writes a measurement archive. Until round 42 the board was never
# reachable here, so the check only ever exercised the offline path; now that it is up,
# the dry run is what gets exercised (it prints the plan and exits 0).
base = [sys.executable, os.path.join(REPO, "tools", "chunk_sweep.py"),
        "--input", os.path.join(REPO, "data", "itch_1m.mold64")]
if reachable:
    r2 = subprocess.run(base, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", env=env, timeout=300)
    out2 = (r2.stdout or "") + (r2.stderr or "")
    dry_ok = ("dry run" in out2) and (r2.returncode == 0) and ("CHUNK-SWEEP-PASS" not in out2)
    print()
    print("  chunk_sweep.py (no --run, board up)")
    print("     returned with exit %d, prints a plan: %s"
          % (r2.returncode, "dry run" in out2))
    if not dry_ok:
        fails.append("chunk_sweep dry run does not print a plan and exit 0")
else:
    r2 = subprocess.run(base + ["--run"], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", env=env, timeout=600)
    out2 = (r2.stdout or "") + (r2.stderr or "")
    claims_pass = "CHUNK-SWEEP-PASS" in out2
    print()
    print("  chunk_sweep.py --run  (board offline)")
    print("     returned with exit %d (did not hang)" % r2.returncode)
    print("     claims CHUNK-SWEEP-PASS: %s (must be False - no board, no data)"
          % claims_pass)
    if claims_pass:
        fails.append("chunk_sweep reports PASS without board data")
    if r2.returncode == 0 and not claims_pass:
        fails.append("chunk_sweep exits 0 without producing a result")

print()
if fails:
    print("RUNBOOK-EXERCISE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("RUNBOOK-EXERCISE-PASS (documented commands fail the way the runbook says)")
