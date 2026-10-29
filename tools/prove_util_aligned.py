"""The util plant could not react: check_util_doc skips when the builds differ.

    document cites bitstream : 4BB3D7D1
    impl_1 produced          : 0ADD08282161F4781133FB6CE3F355F8
    -> UTIL-DOC-SKIPPED (different build)

Round 85 established this is correct: the report's section 4.1 table presents three builds and
its headline figures belong to 4BB3D7D1, while impl_1 holds 0ADD0828. Comparing them would be
comparing two placements of the same RTL.

So editing the table's LUT cell cannot make this check react on the current tree - and that is
by design, not a gap. The check DOES react when the builds are aligned, proven in round 85 by
pointing the report's cited MD5 at impl_1 and then editing the LUT:

    LUT  doc 4111   actual 4499   MISMATCH
    UTIL-DOC-FAIL (1)

### What this round actually established

Of three planted contradictions, two fired once the plant was in the right form:

    book        add=15334 -> 15335                check_internal_consistency fired
    throughput  2,230,335 -> 9,999,999            check_throughput_pair fired
    util        table LUT -> 12,345               no reaction, BY DESIGN (build mismatch)

And earlier, the T1 and WNS plants fired too (check_t1_claims, check_stale_pending,
audit_clock_docs).

So the "three checks never react" conclusion was wrong in all three cases: two were bad plants,
one is a deliberate skip.

### The count of bad instruments this round

    1  docstring-vs-code word scan         62 candidates, all noise
    2  literal-occurrence scan             44 candidates, all output tokens
    3  prose plants in the wrong form      3 "gaps", 2 bad plants
    4  a plant against a skipping check    1 "gap", by design

Four attempts before the method produced a true answer. The method that works is: plant in the
FORM the document uses, against a check that is not deliberately skipping, and watch the exit
code.
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
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# util, with the builds aligned as round 85 did.
BACKTICK = chr(96)
idx = original.find("MD5 " + BACKTICK + "4BB3D7D1")
if idx == -1:
    print("UTIL-ALIGNED-PROOF-FAIL (MD5 anchor not found)")
    sys.exit(1)
start = idx + len("MD5 " + BACKTICK)
# Round 166: cite impl_1's build so check_util_doc proceeds to compare rather than skipping on a build
# mismatch - it now searches for that id anywhere in the document and compares case-insensitively.
aligned = original[:start] + "C6D4E80E" + original[start + 8:]
# DERIVED (round 203): the LUT figure changes on every rebuild. Match the row, not the number.
m = re.search(r"\| LUT \| \*\*(\d[\d,]*)\*\*", aligned)
if not m:
    print("UTIL-ALIGNED-PROOF-FAIL (LUT table cell not found)")
    sys.exit(1)
mutated = aligned[:m.start()] + "| LUT | **12,345**" + aligned[m.end():]

bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "check_util_doc.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    caught = r.returncode != 0
    for l in out.splitlines():
        if "LUT" in l or "FAIL" in l:
            print("   %s" % l.strip()[:88])
    print("   exit=%d %s" % (r.returncode, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

print()
r2 = subprocess.run([sys.executable, os.path.join(TOOLS, "check_util_doc.py")],
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
print("restored exit=%d" % r2.returncode)

if caught and r2.returncode == 0:
    print("UTIL-ALIGNED-PROOF-PASS (a mutated LUT figure is caught when the report cites impl_1)")
    sys.exit(0)
print("UTIL-ALIGNED-PROOF-FAIL")
sys.exit(1)
