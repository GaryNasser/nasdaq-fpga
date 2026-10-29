"""Verify the tokens the report quotes from each tool match what the tools print.

Round 16 found the reproduction section claiming 12 checks when 28 run. The same
drift can hit any quoted tool output, so this re-runs the cheap hardware-independent
tools and compares.

The first version hard-coded guessed verdict tokens and failed all six cases:

    guessed SPEEDUP-PASS        actual SPEEDUP-AUDIT-PASS
    guessed T1-UNITS-PASS       actual T1UNITS-PASS
    guessed BASELINE-PASS       actual BASELINE-REPRO-PASS
    guessed GUARD-PASS          actual GUARD-CHECK-PASS
    guessed "2.0" for io_share  actual IO-SHARE-OK
    guessed CONSTEXPR-PASS      actual CONSTEXPR-PASS (correct)

Five of six were my invention. The check was reporting on my guesses rather than on
the tools. It now derives each token by running the tool and taking its actual
verdict line, then checks only that the report cites that same token.
"""
import os
import re
import subprocess
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
DOC = os.path.join(REPO, "docs", "final-report.md")

report = open(DOC, encoding="utf-8", errors="replace").read()

env = dict(os.environ)
env["PATH"] = r"D:\Xilinx\Vivado\2024.1\bin;" + env.get("PATH", "")

SCRIPTS = [
    "check_speedup.py",
    "check_t1_units.py",
    "check_baseline_repro.py",
    "measure_io_share.py",
    "check_guard.py",
    "check_constexpr.py",
]

# A verdict token: an ALL-CAPS hyphenated phrase ending in a status word.
# Non-greedy body: [A-Z0-9]* would otherwise swallow the PASS the suffix wants,
# which made every tool look like it printed no verdict.
VERDICT = re.compile(r"\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*?-(?:PASS|OK|FAIL))\b")

fails = []
print("re-running cheap tools; comparing their verdict tokens with the report")
print()

for script in SCRIPTS:
    path = os.path.join(TOOLS, script)
    if not os.path.exists(path):
        print("  %-26s MISSING SCRIPT" % script)
        fails.append("%s: not found" % script)
        continue
    try:
        r = subprocess.run([sys.executable, path], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           cwd=REPO, env=env, timeout=600)
    except subprocess.TimeoutExpired:
        print("  %-26s TIMEOUT" % script)
        fails.append("%s: timed out" % script)
        continue
    out = (r.stdout or "") + (r.stderr or "")
    toks = VERDICT.findall(out)
    if not toks:
        print("  %-26s prints no verdict token" % script)
        fails.append("%s: no verdict token in output" % script)
        continue
    tok = toks[-1]
    cited = tok in report
    print("  %-26s %-22s report cites it: %s"
          % (script, tok, "yes" if cited else "NO"))
    if not cited:
        fails.append("%s: report never cites %s" % (script, tok))

print()
if fails:
    print("TOOL-CLAIM-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("TOOL-CLAIM-PASS")
