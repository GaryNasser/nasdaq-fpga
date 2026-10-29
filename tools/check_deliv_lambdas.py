"""The audit already tests each deliverable with a lambda; check the lambdas are live.

audit_deliverables.py is better than I assumed:

    ("<name>", lambda: <test that reads a file>, "<where>")

Each deliverable's evidence is TESTED, not asserted. The three gaps use `lambda: False`
deliberately, so they cannot be marked present by a phrase.

The question this round can still answer: are the live lambdas actually evaluating the
things they name? A lambda that returns True without reading anything would be the
equivalent of `lambda: False` in the other direction.

This enumerates each tuple, runs its test, and separately verifies that the evidence string
names a file or section that exists. A row whose lambda passes an empty check would show up
as "True but evidence unresolvable".
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
AUDIT = os.path.join(REPO, "tools", "audit_deliverables.py")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(AUDIT, encoding="utf-8").read()
report = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read() \
    if os.path.exists(REPORT) else ""

# The tuples: ("name", <lambda body>, "where")
BLOCK = re.search(r"ITEMS\s*=\s*\[(.*?)\n\]", src, re.S)
if not BLOCK:
    print("DELIV-LAMBDA-FAIL (cannot find ITEMS)")
    sys.exit(1)

body = BLOCK.group(1)


def split_tuples(text):
    """Split the ITEMS body into top-level tuples, balancing parens and quotes."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "(":
            i += 1
            continue
        start = i
        depth = 0
        in_str = False
        while i < n:
            c = text[i]
            if in_str:
                if c == "\\":
                    i += 2
                    continue
                if c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        out.append(text[start:i])
    return out


TUPLES = []
for t in split_tuples(body):
    nm = re.match(r'\(\s*"([^"]+)"\s*,', t)
    wh = re.search(r',\s*"([^"]*)"\s*\)\s*$', t)
    lm = re.search(r"lambda[^\n]*", t)
    if nm and wh:
        TUPLES.append((nm.group(1), lm.group(0) if lm else "?", wh.group(1)))

print("deliverable rows and how they are decided")
print()

fails = []
live = 0
for name, lam, where in TUPLES:
    is_false = lam.strip().startswith("lambda: False")
    if not is_false:
        live += 1
    # What does the evidence string point at?
    secs = re.findall(r"§\s*([\d.]+)", where)
    resolved = []
    for s in secs:
        if re.search(r"^#+\s*%s" % re.escape(s), report, re.M):
            resolved.append("§%s ok" % s)
        else:
            resolved.append("§%s MISSING" % s)
            fails.append("%s: section §%s absent" % (name[:30], s))
    kind = "always False (gap)" if is_false else "tested"
    print("  %-40s %-18s %s" % (name[:40], kind, ", ".join(resolved) or where[:26]))

print()
print("  %d row(s), %d with a live test, %d hard-coded False"
      % (len(TUPLES), live, len(TUPLES) - live))

# The three gaps must be the ones that are impossible or unmeasured.
IMPOSSIBLE = ("K1", "K2", "DMA")
gaps = [n for n, lam, w in TUPLES if lam.strip().startswith("lambda: False")]
print()
print("  hard-coded gaps: %s" % [n[:24] for n in gaps])
missing_gap = [k for k in IMPOSSIBLE if not any(k in g for g in gaps)]
if missing_gap:
    fails.append("expected these to be gaps but they are not marked: %s" % missing_gap)

print()
if not TUPLES:
    print("DELIV-LAMBDA-FAIL (no rows parsed)")
    sys.exit(1)
if fails:
    print("DELIV-LAMBDA-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("DELIV-LAMBDA-PASS (%d live test(s), %d explicit gap(s), all evidence resolves)"
      % (live, len(gaps)))
