"""Which verification tools reimplement what they claim to test?

Round 193: `mock_board_recover.py` reimplemented `board_recover.verdict()` and tested its own copy, so it reported
a defect that had been fixed. Two rounds earlier, the same shape appeared in the arithmetic audit: my
`figure_provenance` sweep and `check_arithmetic` both parse the report, and they could disagree.

### The detectable signature

A script that:
    names another tool's function or marker in its docstring/comments   ("demonstrate that X's verdict..."),
    AND does not import from that tool,
    AND re-derives the same behaviour from strings.

That combination is a reimplementation. It is not always wrong - a prover may deliberately re-derive an
expectation independently - **but it must be independent for a reason, and that reason should be visible.**

### What this reports

Scripts that mention a checker/verifier by name without importing it, grouped by the tool they reference, so a
person can look at each and decide whether the independence is deliberate.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

scripts = sorted(f for f in os.listdir(TOOLS) if f.endswith(".py"))

# What each tool exports that another might reimplement.
TARGETS = ["verdict", "GOLDEN-OK", "BOOK-COUNTERS", "SUITE-PASS", "SIMSUITE-PASS"]

rows = []
for fn in scripts:
    src = io.open(os.path.join(TOOLS, fn), encoding="utf-8", errors="replace").read()
    code = re.sub(r'""".*?"""', "", src, flags=re.S)
    code_nc = re.sub(r"#[^\n]*", "", code)

    hits = [t for t in TARGETS if t in code_nc]
    if not hits:
        continue

    # Does it import from a sibling tool?
    imports = re.findall(r"from\s+(\w+)\s+import|import\s+(\w+)", code_nc)
    sib = [a or b for a, b in imports if (a or b) not in
           ("os", "sys", "re", "io", "json", "glob", "subprocess", "hashlib",
            "argparse", "struct", "datetime", "shutil", "tempfile", "collections",
            "time", "math", "random", "textwrap")]
    sibling_imports = [s for s in sib if os.path.exists(os.path.join(TOOLS, s + ".py"))]

    rows.append((fn, hits, sibling_imports))

print("%-32s %-34s %s" % ("script", "references", "imports from"))
print("-" * 88)
for fn, hits, sib in rows:
    print("%-32s %-34s %s" % (fn[:32], ",".join(hits)[:34], ",".join(sib) or "(none)"))

print()
suspicious = [r for r in rows if not r[2]]
print("scripts referencing another tool's output WITH NO sibling import: %d" % len(suspicious))
for fn, hits, _ in suspicious:
    print("  %-32s %s" % (fn, ",".join(hits)))
print()
# Classified in round 194. The families below are independent BY DESIGN; the round-193 defect was a
# fourth kind - a script that re-derived a DECISION and compared it to a second re-derivation.
FAMILY = {
    "mutate_": "edits the real tool's source; the check must then fail",
    "prove_":  "runs a scenario end to end through the shipped path",
    "check_":  "parses a marker out of a log; reading a marker is not reimplementing its producer",
    "run_":    "is itself the producer of the marker",
    "gen_":    "consumes suite output",
    "sweep_":  "drives a parameter sweep",
    "harden_": "modifies and re-runs",
    "measure_": "consumes a log",
}


def _family(fn):
    for p, why in FAMILY.items():
        if fn.startswith(p):
            return why
    return None


# Producers and searchers without a family prefix. Named individually so a NEW unnamed script still fails.
NAMED = {
    "board_recover.py":  "produces the verdict and the GOLDEN-OK marker; it is what others test",
    "mock_run.py":       "fabricates a run to exercise the consumers of those markers",
    "audit_reimpl.py":   "the audit itself; it names the markers because it searches for them",
    "audit_selfcompare.py": "searches tool sources for self-comparison; names them because it searches",
    "audit_tracking.py":  "audits which paths git tracks; names dirs because it searches them",
}

unclassified = []
for fn, hits, _ in suspicious:
    why = _family(fn) or NAMED.get(fn)
    if why is None:
        unclassified.append((fn, hits))

print("classified by family:")
for fn, hits, _ in suspicious:
    why = _family(fn) or NAMED.get(fn)
    print("  %-32s %s" % (fn, why or "(UNCLASSIFIED)"))

print()
if unclassified:
    print("REIMPL-AUDIT-REVIEW (%d unclassified)" % len(unclassified))
    for fn, hits in unclassified:
        print("  %-32s %s" % (fn, ",".join(hits)))
    print()
    print("  A new script must either fall into a known family or state why its independence is deliberate.")
    sys.exit(1)

print("REIMPL-AUDIT-PASS (every cross-tool reference belongs to a family that is independent by design)")
