"""Run each board-touching check once while the board is offline and classify what it does.

Three behaviours are acceptable:

  SKIP    - says the board is absent and exits 0                        (correct)
  PASS    - does not actually need the board for this assertion        (correct, if true)
  INCONC. - says the evidence cannot be gathered, exits 0 with a reason (correct)

One is not:

  FAIL    - reports a design defect when the board is merely absent     (a hardware outage read as a defect)
"""
import io
import os
import re
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
RUNNER = os.path.join(TOOLS, "run_checks.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(RUNNER, encoding="utf-8").read()
refs = dict(re.findall(r'"(\w+)":\s*"([\w.]+\.py)"', src))

TARGETS = ["board_archive_proof", "board_run_location", "boardlog_proof", "input_probe",
           "mutate_hw_provenance_proof", "mutate_input_probe_proof", "pair_guard_proof",
           "reimpl_proof", "runbook_exercise", "verdict_proof"]

OFFLINE = re.compile(r"UNREACHABLE|offline|not reachable|no board|board absent|timeout", re.I)

print("%-28s %-5s %-12s %s" % ("check", "exit", "classification", "evidence"))
print("-" * 92)
bad = []
for name in TARGETS:
    script = refs.get(name)
    if not script:
        continue
    p = os.path.join(TOOLS, script)
    if not os.path.exists(p):
        continue
    try:
        r = subprocess.run([sys.executable, p], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=TOOLS, timeout=300)
        out = (r.stdout or "") + (r.stderr or "")
        rc = r.returncode
    except subprocess.TimeoutExpired:
        print("%-28s %-5s %-12s %s" % (name, "-", "TIMEOUT", "gave up after 300 s"))
        bad.append((name, "timeout"))
        continue

    says_absent = bool(OFFLINE.search(out))
    tail = [l.strip() for l in out.split("\n") if l.strip()]
    tail = tail[-1][:42] if tail else "(no output)"

    if rc == 0:
        cls = "SKIP/PASS"
    elif says_absent:
        cls = "*** FAIL ***"
        bad.append((name, tail))
    else:
        cls = "*** FAIL ***"
        bad.append((name, tail))
    print("%-28s %-5d %-12s %s" % (name, rc, cls, tail))

print()
if bad:
    print("BOARD-OFFLINE-FAIL (%d check(s) misreport an absent board)" % len(bad))
    for n, why in bad:
        print("  %-28s %s" % (n, why))
    sys.exit(1)
print("BOARD-OFFLINE-PASS (no check turns an absent board into a design defect)")
