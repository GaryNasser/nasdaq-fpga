"""Which checks have a proof that they fail for the RIGHT reason, and which have only "it can exit non-zero"?

Round 214 established that all 177 checks have a reachable failing exit. **That is the weak property.** The strong
one is: mutate what the check is supposed to catch, and confirm it catches exactly that - and nothing else.

A permanent proof does three things:
    1  breaks the subject in a way the check should notice
    2  asserts the check fails
    3  restores the subject and asserts the check passes again

This lists, per registered check, whether such a proof exists.
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
refs = dict(re.findall(r'"(\w+)":\s*"([\w.]+\.py)"', src))

# A proof names its subject either by invoking the checker or by naming its script.
proof_files = [f for f in os.listdir(TOOLS)
               if f.endswith(".py") and (f.startswith("prove_") or f.startswith("mutate_"))]

covered = {}
# A check whose own script is a prove_/mutate_ file IS the proof - it mutates and asserts.
for name, script in refs.items():
    if script.startswith(("prove_", "mutate_", "audit_")):
        covered.setdefault(name, []).append(script + " (is the proof)")

# Round 249: only a proof that RUNS counts. A `mutate_*` file that no registered script invokes is a dead
# proof - it asserts the right thing and never executes. Record those separately.
_registered_scripts = set(refs.values())
_bodies = {s: io.open(os.path.join(TOOLS, s), encoding="utf-8", errors="replace").read()
           for s in _registered_scripts if os.path.exists(os.path.join(TOOLS, s))}

dead_proofs = []
for pf in proof_files:
    body = io.open(os.path.join(TOOLS, pf), encoding="utf-8", errors="replace").read()
    runs = pf in _registered_scripts or any(pf[:-3] in b for b in _bodies.values())
    for name, script in refs.items():
        if script in body or ('"%s"' % name) in body:
            if runs:
                covered.setdefault(name, []).append(pf)
            else:
                dead_proofs.append((name, pf))

print("%-24s %-34s %s" % ("check", "script", "proven by"))
print("-" * 96)
uncovered = []
for name in sorted(refs):
    proofs = covered.get(name, [])
    print("%-24s %-34s %s" % (name[:24], refs[name][:34], ",".join(sorted(set(proofs))[:2]) or "(none)"))
    if not proofs:
        uncovered.append(name)

print()
print("checks examined : %d" % len(refs))
print("with a proof    : %d" % (len(refs) - len(uncovered)))
print("without a proof : %d" % len(uncovered))
print()
print("dead proofs (named a check but never executed): %d" % len({pf for _, pf in dead_proofs}))
_missing = sorted({pf for _, pf in dead_proofs} - set(refs.values()))
for pf in _missing[:12]:
    print("  " + pf)
if len(_missing) > 12:
    print("  ... and %d more" % (len(_missing) - 12))
print()
print("proof files: %d" % len(proof_files))
for pf in sorted(proof_files):
    n = sum(1 for v in covered.values() if pf in v)
    if n:
        print("  %-34s covers %d check(s)" % (pf, n))
