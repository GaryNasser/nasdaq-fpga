"""The scan asks "can this file exit non-zero", not "can its FAIL branch".

check_golden.py contains an early `raise SystemExit("no BOOK-COUNTERS line in baseline")`
for a missing input. That is a non-zero exit, and my scan counted it - so removing the
sys.exit(1) after the FAIL branch went undetected.

The distinction that matters:

    failing because the input is missing / unreadable   -> a parse error, not a verdict
    failing because the check found problems            -> the verdict

A checker can have the first without the second, and that is precisely check_golden's old
bug: broken input fails loudly, a wrong golden constant passes silently.

So the scan must look for a non-zero exit that is reachable FROM the FAIL path. A
conservative textual test: does a non-zero exit appear at or after the first line that
prints a FAIL token?
"""
import glob
import io
import os
import re
import sys

TOOLS = r"D:\agent\nasdaq-fpga\tools"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FAIL_PRINT = re.compile(r'print\(\s*["\'][A-Z0-9\-]*FAIL')
EXIT_CALL = re.compile(r"(?:sys\.exit|SystemExit)\(")


def nonzero_exits_after_fail(src):
    """Offsets of non-zero exits that occur at or after the first FAIL print."""
    m = FAIL_PRINT.search(src)
    if not m:
        return None
    start = m.start()
    found = []
    for em in EXIT_CALL.finditer(src):
        if em.start() < start:
            continue
        i = em.end()
        depth = 1
        while i < len(src) and depth:
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
            i += 1
        arg = src[em.end():i - 1].strip()
        if arg and not re.fullmatch(r"0|None", arg):
            found.append(arg)
    return found


files = sorted(glob.glob(os.path.join(TOOLS, "check_*.py")))
print("checkers whose FAIL branch cannot exit non-zero")
print()

bad = []
examined = 0
for path in files:
    name = os.path.basename(path)
    src = io.open(path, encoding="utf-8", errors="replace").read()
    if not FAIL_PRINT.search(src):
        continue
    examined += 1
    exits = nonzero_exits_after_fail(src)
    if not exits:
        bad.append(name)
        print("  %-34s no non-zero exit at or after the FAIL print" % name)

print()
print("  %d checker(s) with a FAIL branch examined" % examined)

if bad:
    print()
    print("EXIT-REACHABLE-FAIL (%d)" % len(bad))
    for n in bad:
        print("  " + n)
    print()
    print("  A checker whose only non-zero exits are input-parse errors cannot report")
    print("  a wrong result. The suite records PASS for its FAIL output.")
    sys.exit(1)
print("EXIT-REACHABLE-PASS")
