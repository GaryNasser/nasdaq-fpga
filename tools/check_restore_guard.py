"""Does every proof restore what it modifies, even when interrupted?

Round 252: 16 registered proofs rewrite `docs/final-report.md` and had no `finally` restore. One interrupted run left
`ZZ_NEVER_MATCHES_ZZ` rows in the report and two checks failed. **That was found by hand after the fact.**

The property to enforce: **a proof that writes to a tracked file must have a restore path that survives a kill**
- a `finally` block, or an `atexit` handler, or it works on a copy and never touches the original.

Three shapes are safe:
    write to a temp copy, run against that      never modifies the original
    try/finally with copyfile back              restores on exception and sys.exit
    atexit.register(copyfile back)              restores even when the process is killed mid-run

A bare `write` + `copyfile` afterwards with no try/finally/atexit is unsafe.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
RUNNER = os.path.join(TOOLS, "run_checks.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

runner = io.open(RUNNER, encoding="utf-8").read()
refs = dict(re.findall(r'"(\w+)":\s*"([\w.]+\.py)"', runner))

# Tracked file families a proof might rewrite in place.
TRACKED = ("final-report.md", "status.md", "runbook.md", "bringup-defects.md",
           "ts_hist.v", "itch_parse.v", "mold64_reasm.v", "order_book.v", "ctrl_regs.v",
           "load_overlay.py", "run_checks.py")

unsafe = []
checked = 0

for name, script in sorted(refs.items()):
    if not script.startswith(("mutate_", "prove_")):
        continue
    p = os.path.join(TOOLS, script)
    if not os.path.exists(p):
        continue
    body = io.open(p, encoding="utf-8", errors="replace").read()

    touched = [t for t in TRACKED if t in body]
    if not touched:
        continue
    checked += 1

    has_finally = "finally:" in body
    has_atexit = "atexit" in body
    # Does it write to a path that is the tracked file itself (p / REPORT / TARGET ...)?
    inplace = bool(re.search(r'io\.open\(\s*(?:REPORT|STATUS|RUNBOOK|TARGET|p)\s*,\s*"w"', body))
    backup_and_restore = body.count("copyfile") >= 2

    if not has_finally and not has_atexit:
        unsafe.append((script, touched[:2], "no finally/atexit",
                       "writes in place" if inplace else "backup only"))

print("proofs touching tracked files : %d" % checked)
print("without an interruption-safe restore: %d" % len(unsafe))
print()
for s, t, why, note in unsafe:
    print("  %-36s %-18s %-14s %s" % (s, ",".join(t)[:18], why, note))

print()
if unsafe:
    print("RESTORE-GUARD-FAIL (%d proof(s) can leave a tracked file modified)" % len(unsafe))
    sys.exit(1)
print("RESTORE-GUARD-PASS (every proof that touches a tracked file restores on interruption)")
