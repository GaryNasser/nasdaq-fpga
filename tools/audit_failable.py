"""For each registered check, ask: could it ever fail? A check whose failure path is unreachable is decoration.

Rounds 191-213 found five checks that could not fail for the right reason:

    191  audit_returns          deleted, and checker_exits caught it
    204  check_bit_repro        baseline was a copy of the thing it checked
    212  check_stale_pending    a regex with backspaces never matched
    212  check_stale_pending    the targeted scan sat after sys.exit(1)
    213  (found by search)      none remaining

**The general question is cheap to ask statically**: does the script contain a path that prints a FAIL token and
exits non-zero, and is that path reachable (not shadowed by an earlier unconditional exit)?

This reports, per registered check:
    the FAIL token it can print
    whether it has an exit(1)/(-1)/raise on the failure path
    whether any exit precedes the first FAIL print
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

src = io.open(RUNNER, encoding="utf-8").read()
section = src.split("SCRIPT", 1)[-1]
refs = re.findall(r'"(\w+)":\s*"([\w.]+\.py)"', section)

rows = []
problems = []
for name, script in refs:
    path = os.path.join(TOOLS, script)
    if not os.path.exists(path):
        problems.append((name, "script missing"))
        continue
    body = io.open(path, encoding="utf-8", errors="replace").read()

    # A FAIL token: an uppercase token ending in FAIL, in a print.
    # A failure token is any uppercase word containing FAIL, inside SOME string literal - the literal may
    # carry a format spec, e.g. "GOLDEN-CONST-FAIL (%d)".
    fails = re.findall(r'"[^"\n]*?([A-Z][A-Z0-9_-]*FAIL[A-Z0-9_-]*)', body)
    fails += re.findall(r"'[^'\n]*?([A-Z][A-Z0-9_-]*FAIL[A-Z0-9_-]*)", body)
    has_fail = bool(fails)

    # Round 250: `sys.exit(0 if ok else 1)` is a reachable failing exit, but the old pattern required the
    # non-zero digit to follow the paren directly - so a conditional exit looked like no exit at all.
    has_exit = bool(re.search(r"raise SystemExit", body))
    for _a in re.findall(r"(?:sys\.)?exit\(([^)\n]*)\)", body):
        _a = _a.strip()
        if not _a or _a == "0":
            continue
        # A literal non-zero somewhere in the expression is enough: `1`, `0 if ok else 1`, `True`, `-1`.
        if re.search(r"\b[1-9]\d*\b", _a) or re.search(r"\bTrue\b", _a):
            has_exit = True
            break

    # Position of the first FAIL print and any exit before it.
    i_fail = body.find("FAIL")
    early_exit = False
    if i_fail > 0:
        head = body[:i_fail]
        # An unconditional sys.exit at module level in the head would shadow everything after.
        for m in re.finditer(r"^sys\.exit\(([^)]*)\)", head, re.M):
            if "if" not in m.group(1) and "fails" not in m.group(1):
                early_exit = True
                break

    rows.append((name, script, has_fail, has_exit, early_exit))
    # Round 214: printing a FAIL token is one way to report; exiting non-zero is the requirement.
    # A check that prints only a PASS token and exits 1 on failure is perfectly sound.
    has_success_token = bool(re.findall(r'"[^"\n]*?(?:PASS|CURRENT|IDENTICAL|OK)\b', body))

    if not has_exit:
        problems.append((name, "no failing exit - cannot fail"))
    elif early_exit:
        problems.append((name, "unconditional exit before the checks"))

print("%-26s %-34s %-8s %-8s %s" % ("check", "script", "FAILtok", "exit!=0", "shadowed"))
print("-" * 96)
for name, script, hf, he, ee in rows:
    if not (hf and he) or ee:
        print("%-26s %-34s %-8s %-8s %s" % (name[:26], script[:34], hf, he, ee))

print()
print("checks examined: %d" % len(rows))
print("with a problem : %d" % len(problems))
for name, why in problems:
    print("  %-28s %s" % (name, why))

print()
if problems:
    print("FAILABLE-AUDIT-FAIL (%d)" % len(problems))
    for name, why in problems:
        print("  %-28s %s" % (name, why))
    print()
    print("  A check with no reachable non-zero exit is decoration: it reports PASS whatever it sees.")
    sys.exit(1)

print("FAILABLE-AUDIT-PASS (every registered check has a reachable failing exit)")
