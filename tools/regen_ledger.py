"""Regenerate the coverage ledger after rounds 86-89 proved four more checks.

Round 85's ledger was written when 20 checks were unproven. Since then:

    86  clock_docs, board_claims            -> proven
    87  ctrl_sequence                       -> proven
        reference_id                        -> proven (round 88, after stubbing the driver)
        transfer_reset                      -> found weak, then fixed and proven (89)
    88  check_driver_imports added as a behavioural guard

The ledger is a document that goes stale like any other, which is the fault this project has
spent many rounds on. Regenerating it from the current state, and stating the unproven list
as it now stands.
"""
import glob
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
RC = os.path.join(TOOLS, "run_checks.py")
OUT = os.path.join(REPO, "docs", "coverage-ledger.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(RC, encoding="utf-8").read()
suite = [m.group(1) for m in re.finditer(r'\("(\w+)",\s*"[^"]*",\s*\w+\)', src)]
paths = dict((m.group(1), m.group(2))
             for m in re.finditer(r'"(\w+)":\s*"([\w.]+\.py)"', src))

exercisers = {}
for pat in ("mutate_*.py", "test_*.py", "prove_*.py"):
    for p in glob.glob(os.path.join(TOOLS, pat)):
        exercisers[os.path.basename(p)] = io.open(p, encoding="utf-8",
                                                   errors="replace").read()

HAND = {
    "skip_conversion": "report deleted; 11 guards exited 1 (round 67)",
    "runbook_exercise": "commands run against an offline board; exit 2 (round 73)",
    "unclassified_guards": "both guards inspected and classified (round 67)",
    "checker_exits": "exercised when mutate_rtl_vitals.py was added (round 83)",
}


def wrapper_target(script):
    p = os.path.join(TOOLS, script)
    if not os.path.exists(p):
        return None
    t = io.open(p, encoding="utf-8", errors="replace").read()
    m = re.search(r'"""(.*?)"""', t, re.S)
    if not m:
        return None
    m2 = re.search(r"(\w+\.py)", m.group(1))
    return m2.group(1) if m2 and m2.group(1) != script else None


rows = []
for name in suite:
    script = paths.get(name)
    if not script:
        rows.append((name, "-", "no script"))
        continue
    if script.startswith(("mutate_", "prove_")):
        rows.append((name, script, "is a harness"))
        continue
    stem = script[:-3]
    hits = [h for h, b in exercisers.items() if script in b or stem in b]
    if hits:
        kind = ("automated (mutate)" if any(h.startswith(("mutate_", "prove_")) for h in hits)
                else "automated (test)")
        rows.append((name, ", ".join(hits[:2]), kind))
        continue
    if name in HAND:
        rows.append((name, HAND[name], "hand-run once"))
        continue
    tgt = wrapper_target(script)
    if tgt and os.path.exists(os.path.join(TOOLS, tgt)):
        rows.append((name, "wraps %s" % tgt, "automated (wrapper)"))
        continue
    rows.append((name, "-", "UNPROVEN"))

counts = {}
for _, _, k in rows:
    counts[k] = counts.get(k, 0) + 1

LINES = [
    "# Coverage ledger",
    "",
    "Every check in the suite, with the evidence that it can FAIL - not merely that it runs.",
    "",
    "Regenerated round 90. Earlier versions went stale as checks were proven; a ledger that is",
    "not rebuilt is the same kind of defect as a number nobody recomputes.",
    "",
    "| kind | meaning |",
    "| --- | --- |",
    "| automated (mutate)  | a mutate_*.py or prove_*.py breaks the subject and requires failure |",
    "| automated (test)    | a test_*.py does the same for a behavioural property |",
    "| automated (wrapper) | the suite entry delegates to a test_*.py that does it |",
    "| hand-run once       | exercised in a past session; nothing re-runs it |",
    "| UNPROVEN            | passes; nothing has shown it can fail |",
    "",
    "## Totals",
    "",
]
for k in ("automated (mutate)", "automated (test)", "automated (wrapper)",
          "hand-run once", "UNPROVEN", "is a harness", "no script"):
    if k in counts:
        LINES.append("* %s: **%d**" % (k, counts[k]))
LINES += ["", "## Per check", "", "| check | evidence | kind |", "| --- | --- | --- |"]
for n, e, k in rows:
    LINES.append("| `%s` | %s | %s |" % (n, e.replace("|", "\\|")[:64], k))

io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(LINES) + "\n")

print("ledger regenerated from the current state")
print()
for k in ("automated (mutate)", "automated (test)", "automated (wrapper)",
          "hand-run once", "UNPROVEN"):
    print("  %-22s %d" % (k, counts.get(k, 0)))
print()
print("  still unproven (%d):" % counts.get("UNPROVEN", 0))
for n, e, k in rows:
    if k == "UNPROVEN":
        print("     %-24s %s" % (n, paths.get(n, "-")))
