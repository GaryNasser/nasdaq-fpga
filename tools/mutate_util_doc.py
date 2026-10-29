import re
"""The util_doc skip is correct; my mutation was invalid.

The check reports:

    document cites bitstream : 4BB3D7D1
    impl_1 produced          : 0ADD08282161F4781133FB6CE3F355F8
    -> different build; resource numbers are not comparable

That is right. The report's section 4.1 table presents three builds:

    4BB3D7D1 (shipped, 17:56)   D874BD51 (rebuild)   0ADD0828 (current, 23:27)

and its headline utilisation figures belong to 4BB3D7D1, while impl_1 holds 0ADD0828. The
two are not comparable and the check declines to compare them - which is what round 48 built
it to do.

So changing a 4,499 in the report cannot make it fail: 4,499 is a 0ADD0828 figure, and the
check is not comparing that build's numbers. The mutation tested a comparison the check
deliberately does not make.

This is the same category as round 83's ITCH_TYPE_ADD mutation and round 84's three failed
classifications: **a mutation that expects failure from a check scoped elsewhere proves
nothing about the check.**

What IS worth confirming: that the skip is a decision, not an accident. The output shows the
two MD5s and the reason, which is the evidence. And the report's claim that 4,499 belongs to
0ADD0828 can be checked directly against impl_1's report - which the deliverable audit now
does since round 81.

So the honest ledger entry for util_doc is: skips by design when the builds differ; the
comparison it performs applies to whichever build impl_1 holds.

Recording that, and dropping the invalid mutation.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
CHECK = os.path.join(TOOLS, "check_util_doc.py")
DOC = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 1. Document the scoping decision in the check.
src = io.open(CHECK, encoding="utf-8", errors="replace").read()
if "SCOPE:" not in src:
    m = re.search(r'"""(.*?)"""', src, re.S)
    if m:
        body = m.group(1)
        add = (body.rstrip()
               + "\n\nSCOPE: the comparison only runs when the report cites the SAME bitstream\n"
               "impl_1 holds. The report presents three builds; its headline resource figures\n"
               "belong to 4BB3D7D1 while impl_1 holds 0ADD0828, so this skips rather than\n"
               "compare incomparable numbers. A mutation that edits a figure belonging to the\n"
               "other build therefore cannot fail this check - by design.\n")
        src = src.replace('"""' + body + '"""', '"""' + add + '"""', 1)
        compile(src, CHECK, "exec")
        io.open(CHECK, "w", encoding="utf-8", newline="\n").write(src)
        print("scope documented in check_util_doc")

# 2. Prove the comparison DOES fail when the builds agree, by editing a figure.
#
# Round 166: the report now cites impl_1's build directly, so no MD5 rewrite is needed to make them
# agree - check_util_doc finds the match on its own. Rewriting the shipped build's id (as this used to)
# now only makes the document self-contradictory.
rep = io.open(DOC, encoding="utf-8", errors="surrogateescape").read()
# DERIVED (round 203): find the LUT cell by pattern, and ASSUME NOTHING about the current figure.
LUT_CELL_RE = re.compile(r"(\| LUT \| \*\*)(\d[\d,]*)(\*\*)")
_m = LUT_CELL_RE.search(rep)
if not _m:
    print("UTIL-DOC-MUTATION-FAIL (no LUT cell found in the report)")
    sys.exit(1)
_true_lut = _m.group(2)
_wrong_lut = "4,111" if _true_lut != "4,111" else "4,222"
mutated = rep[:_m.start(2)] + _wrong_lut + rep[_m.end(2):]
if mutated == rep:
    print("UTIL-DOC-MUTATION-FAIL (the substitution did not change the report)")
    sys.exit(1)
print("  mutating LUT %s -> %s" % (_true_lut, _wrong_lut))
if mutated == rep:
    print("UTIL-DOC-MUTATION-FAIL (the LUT figure 4,502 was not found in the report)")
    raise SystemExit(1)

bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(DOC, bk)
try:
    io.open(DOC, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    caught = r.returncode != 0
    print()
    print("  with the builds aligned and a wrong LUT figure:")
    for l in out.splitlines():
        if l.strip():
            print("     %s" % l.strip()[:88])
    print("  exit=%d %s" % (r.returncode, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, DOC)
    os.unlink(bk)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print()
print("  restored exit=%d" % r.returncode)
print()
if caught and r.returncode == 0:
    print("UTIL-DOC-MUTATION-PASS")
    sys.exit(0)

print("UTIL-DOC-MUTATION-FAIL")
sys.exit(1)
