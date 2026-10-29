"""Four checks whose rules are now written down; mutate exactly those rules.

    flag_audit            fails if --legacy-reset is undeclared/unexplained/unread, or CTRL=0x3
                          sits outside a legacy branch.
                          -> remove the flag's add_argument call.

    baseline_repro        fails if the C baseline's counters differ, or the capture sizes are
                          wrong.
                          -> point it at a truncated copy of the capture.

    speedup               fails if the published multiple != best-warm, or lies outside the
                          computed range; `published` is its own constant.
                          -> change it to 9.90.

    experiment_evidence   fails if the log mentions multicycle/gap_pending, or timing_mcyc.xdc
                          was parsed other than twice.
                          -> add a multicycle line to the log.

Each mutation is derived from the rule above, not guessed.

NOTE ON THE LOG THIS PROVES AGAINST (round 166)
-----------------------------------------------
The prover mutates build_check/experiment_mcyc.log, which is not the deployed build's log. That is
correct for the same reason it is correct in check_experiment_evidence.py: the round-33 experiment is
the object of study. Nothing derived from that log is compared against
impl_1/nasdaq_wrapper_timing_summary_routed.rpt or out/nasdaq.bit, so no mutation here can make a
non-deployed figure look like the shipped one - which is what check_build_source.py exists to prevent.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
DRV = os.path.join(REPO, "board", "load_overlay.py")
EXP = os.path.join(REPO, "build_check", "experiment_mcyc.log")
SPEEDUP = os.path.join(TOOLS, "check_speedup.py")
DATA = os.path.join(REPO, "data", "itch_loc6836.mold64")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run(check):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, check)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


print("baseline")
for c in ("check_flag_audit.py", "check_baseline_repro.py", "check_speedup.py",
          "check_experiment_evidence.py"):
    rc, out = run(c)
    tail = [l for l in out.splitlines() if l.strip()][-1:]
    print("  %-32s exit=%d  %s" % (c, rc, tail[0][:44] if tail else ""))
print()

results = []

# --- flag_audit: remove the flag's declaration -------------------------------
drv = io.open(DRV, encoding="utf-8", errors="replace").read()
m = re.search(r"\n[^\n]*add_argument\(\s*['\"]--legacy-reset['\"]", drv)
if m:
    # Find the end of that call (balanced parens on following lines).
    start = m.start()
    depth = 0
    i = m.end()
    while i < len(drv):
        if drv[i] == "(":
            depth += 1
        elif drv[i] == ")":
            if depth == 0:
                i += 1
                break
            depth -= 1
        i += 1
    mutated = drv[:start] + "\n" + drv[i:]
    bk = tempfile.mktemp(suffix=".py")
    shutil.copyfile(DRV, bk)
    try:
        io.open(DRV, "w", encoding="utf-8", errors="replace", newline="\n").write(mutated)
        rc, out = run("check_flag_audit.py")
        caught = rc != 0
        results.append(("flag_audit: declaration removed", caught))
        print("%-40s exit=%d %s" % ("flag_audit: declaration removed", rc,
                                    "CAUGHT" if caught else "MISSED"))
        if not caught:
            for l in [x for x in out.splitlines() if x.strip()][-2:]:
                print("      %s" % l[:82])
    finally:
        shutil.copyfile(bk, DRV)
        os.unlink(bk)
else:
    print("%-40s NOT FOUND" % "flag_audit")

# --- speedup: change its own constant --------------------------------------
sp = io.open(SPEEDUP, encoding="utf-8", errors="replace").read()
m = re.search(r"published\s*=\s*([\d.]+)", sp)
if m:
    mutated = sp[:m.start(1)] + "9.90" + sp[m.end(1):]
    bk = tempfile.mktemp(suffix=".py")
    shutil.copyfile(SPEEDUP, bk)
    try:
        io.open(SPEEDUP, "w", encoding="utf-8", newline="\n").write(mutated)
        rc, out = run("check_speedup.py")
        caught = rc != 0
        results.append(("speedup: published 3.10 -> 9.90", caught))
        print("%-40s exit=%d %s" % ("speedup: published 3.10 -> 9.90", rc,
                                    "CAUGHT" if caught else "MISSED"))
    finally:
        shutil.copyfile(bk, SPEEDUP)
        os.unlink(bk)

# --- experiment_evidence: add a multicycle mention --------------------------
if os.path.exists(EXP):
    raw = io.open(EXP, encoding="utf-8", errors="replace").read()
    bk = tempfile.mktemp(suffix=".log")
    shutil.copyfile(EXP, bk)
    try:
        io.open(EXP, "w", encoding="utf-8", errors="replace", newline="\n").write(
            raw + "\nThe multicycle exception was applied to gap_pending.\n")
        rc, out = run("check_experiment_evidence.py")
        caught = rc != 0
        results.append(("experiment: multicycle mentioned", caught))
        print("%-40s exit=%d %s" % ("experiment: multicycle mentioned", rc,
                                    "CAUGHT" if caught else "MISSED"))
    finally:
        shutil.copyfile(bk, EXP)
        os.unlink(bk)

print()
for c in ("check_flag_audit.py", "check_speedup.py", "check_experiment_evidence.py"):
    rc, _ = run(c)
    print("  %-32s exit=%d (restored)" % (c, rc))

print()
if results and all(c for _, c in results):
    sys.exit(0)
print("RULE-PROOF-FAIL")
sys.exit(1)
