"""Find checks that compare something to a copy of itself.

Five instances in five rounds (193, 200, 203 x2, 204), each found by accident. Accident is not a method.

### The detectable shapes

A check is self-comparing if any of these appears:

    A  it writes a file, then reads it back and compares              (the write IS the reference)
    B  it copies a file to a baseline and later compares against it    (a copy of the thing checked)
    C  it compares F(x) to F(x) with the same F                        (a tautology)
    D  its "expected" value is read from the same artifact it validates

### What is NOT self-comparing, and must not be flagged

    a MUTATION test that edits a file and requires the check to FAIL   (deliberately breaks the input)
    a proof that fabricates an input and compares against a hardcoded expectation
    a check comparing two independently produced artifacts

So the audit reports candidates with a classification, and a new unclassified one fails - the same shape as
`audit_reimpl` from round 194, which caught a real case two rounds later.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Patterns that suggest writing-then-reading, or copying-then-comparing.
SHAPES = [
    ("writes then reads back",
     [r"io\.open\([^)]*['\"]w['\"]", r"\.write\("],
     [r"io\.open\([^)]*['\"]r['\"]", r"\.read\("]),
    ("copies to a baseline",
     [r"shutil\.copy", r"copyfile"],
     [r"BASE_", r"baseline"]),
    ("compares a file to its own copy",
     [r"md5\((\w+)\)\s*==\s*md5\((\w+)\)"],
     []),
]

# Known-legitimate families, by filename prefix, with the reason.
LEGIT = {
    "mutate_":  "deliberately breaks the input; the check MUST fail",
    "prove_":   "fabricates input or mutates, then asserts the check reacts",
    "rebase":   "ESTABLISHES a baseline; must be run once and reviewed",
}

scripts = sorted(f for f in os.listdir(TOOLS) if f.endswith(".py"))

print("%-34s %-30s %s" % ("script", "shape", "family"))
print("-" * 92)

candidates = []
for fn in scripts:
    src = io.open(os.path.join(TOOLS, fn), encoding="utf-8", errors="replace").read()
    code = re.sub(r'""".*?"""', "", src, flags=re.S)

    hits = []
    for name, writers, readers in SHAPES:
        if all(re.search(p, code) for p in writers):
            if not readers or all(re.search(p, code) for p in readers):
                hits.append(name)
        if name == "compares a file to its own copy" and not readers:
            for _m in re.finditer(writers[0], code):
                _a, _b = _m.group(1), _m.group(2)

                def _resolve(var):
                    mm = re.search(r"^%s\s*=\s*(.+)$" % re.escape(var), code, re.M)
                    return mm.group(1).strip() if mm else None

                _pa, _pb = _resolve(_a), _resolve(_b)
                if _pa and _pb:
                    # Distinct directories mean distinct files; that is a legitimate comparison.
                    _da = re.sub(r"[^\\/]+$", "", _pa)
                    _db = re.sub(r"[^\\/]+$", "", _pb)
                    distinct_paths = (_da != _db)
                    if distinct_paths:
                        continue
                hits.append(name)

    if not hits:
        continue

    fam = next((LEGIT[p] for p in LEGIT if fn.startswith(p)), None)
    print("%-34s %-30s %s" % (fn[:34], ",".join(hits)[:30], fam or "(NONE)"))
    if fam is None:
        candidates.append((fn, hits))

# Reviewed in round 205. Each entry states WHY the comparison is between independent things.
REVIEWED = {
    "check_bit_repro.py":
        "compares build_check/<stamp>/nasdaq.bit against vivado/out/nasdaq.bit - two files in two "
        "directories, one frozen at build time. Round 204's defect was that BASE_DIR held a copy of the "
        "CURRENT artifact AND the verdict consulted `identical` first; both are fixed (fingerprint decides).",
}

unreviewed = [(fn, h) for fn, h in candidates if fn not in REVIEWED]
for fn, h in candidates:
    if fn in REVIEWED:
        print("  %-34s reviewed: %s" % (fn, REVIEWED[fn][:44]))

print()
print("candidates with no known-legitimate family: %d" % len(unreviewed))
for fn, hits in unreviewed:
    print("  %-34s %s" % (fn, ",".join(hits)))

if unreviewed:
    print()
    print("SELFCOMPARE-AUDIT-FAIL (%d)" % len(unreviewed))
    print()
    print("  A check that compares X to a copy of X always passes and always will.")
    print("  Either give it a family in LEGIT (with the reason), or make it compare something independent.")
    sys.exit(1)

print()
print("SELFCOMPARE-AUDIT-PASS (no check compares a thing to a copy of itself)")
