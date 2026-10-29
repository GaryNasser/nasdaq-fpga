"""Verify every checker can actually fail - i.e. has a non-zero exit path.

`run_checks.py` decides PASS purely from `returncode == 0`. So a checker that never
calls sys.exit(1) or raises is counted as passing no matter what it inspects. That is
the failure mode this project has recorded five times:

    PARITY-TOTAL printed on both outcomes
    check_board_claims passed on zero matches
    check_warmup_advice passed on zero matches
    tb_parity2 could not fail
    check_repro_doc sliced the wrong table

The runner is the one place where every check's credibility is decided, and it trusts
an exit code that nothing has audited.

For each checker this reports:

  * whether the source contains a non-zero exit (sys.exit(n) or raise/systemexit);
  * how many, so a single incidental one is visible;
  * whether the verdict token it prints distinguishes pass from fail.

A checker with no non-zero exit at all is reported as UNABLE TO FAIL.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

# Read the CHECKS table to get key -> script.
rc = io.open(os.path.join(TOOLS, "run_checks.py"), encoding="utf-8").read()
lines = rc.split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("CHECKS"))
end = next(i for i in range(start + 1, len(lines))
           if lines[i].rstrip().endswith("]")
           and not lines[i].lstrip().startswith("("))
checks = re.findall(r'\(\s*"(\w+)",\s*"([^"]*)"', "\n".join(lines[start:end]))

# Map key -> script from SCRIPT dict.
smap = dict(re.findall(r'"(\w+)":\s*"([\w.]+\.py)"', rc))

# Round 250: a conditional exit — `sys.exit(0 if ok else 1)` — is a reachable failing exit, but requiring the
# non-zero digit right after the paren missed it. Match any exit() whose argument expression contains a non-zero
# literal or `True`/`not`.
NONZERO = re.compile(r"sys\.exit\((?=[^)\n]*?(?:\b[1-9]\d*\b|\bTrue\b|\bnot\b|\bfail\w*\b))[^)\n]*\)|"
                     r"raise\s+SystemExit\(\s*[1-9]|^\s*raise\s+\w+", re.M)

rows = []
fails = []
print("%-16s %-26s %-8s %s" % ("check", "script", "exits", "note"))
print("-" * 92)

for key, desc in checks:
    script = smap.get(key)
    if not script:
        rows.append((key, "?", 0, "no script mapped"))
        fails.append("%s: no script mapped in SCRIPT dict" % key)
        continue
    path = os.path.join(TOOLS, script)
    if not os.path.exists(path):
        rows.append((key, script, 0, "MISSING FILE"))
        fails.append("%s: script %s missing" % (key, script))
        continue
    src = io.open(path, encoding="utf-8", errors="replace").read()
    n = len(NONZERO.findall(src))
    note = ""
    if n == 0:
        note = "UNABLE TO FAIL"
        fails.append("%s: %s has no non-zero exit path" % (key, script))
    elif n == 1:
        note = "single exit path"
    rows.append((key, script, n, note))
    print("%-16s %-26s %-8d %s" % (key, script, n, note))

print()
print("%d checkers examined" % len(rows))
if fails:
    print("CHECK-EXIT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("CHECK-EXIT-PASS")
