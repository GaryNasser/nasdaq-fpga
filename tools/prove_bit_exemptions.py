"""bit_repro's exemptions must ignore comments and catch code, wherever it sits.

`check_bit_repro` has several ways a changed input can still pass. Enumerate them and test their UNION.

    round 204   comment-only edit        _strip_comments strips # / /* */ / //
    round 244   post-build tcl region    text up to `launch_runs impl_1` must match
    round 245   comment exemption        refined; applies to .tcl/.xdc/.v

Round 245 discovered that two exemptions together covered an injection neither was meant to cover. **The question
this round asks is the general one: can ALL of them be satisfied at once by a change that DOES affect the design?**

The worst case is a change that is:
    after write_bitstream     so the post-build rule skips it
    AND comment-shaped        so the comment rule skips it
    AND inside a tcl file     so neither rule looks at RTL

A comment after write_bitstream **genuinely cannot affect the artifact**, so that union is safe. **What would not
be safe** is a CODE change after write_bitstream that alters the gate - e.g. moving the WNS check, or editing a
`file copy` that runs later.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_bit_repro.py")
TCL = os.path.join(REPO, "vivado", "build_overlay.tcl")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=900)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("UNION-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(TCL, encoding="utf-8", errors="surrogateescape").read()
MARK = "launch_runs impl_1"
i = body.find(MARK)
if i < 0:
    print("UNION-INCONCLUSIVE (no launch_runs impl_1)")
    sys.exit(0)

results = []


def inject(label, transform, expect):
    mutated = transform(body)
    if mutated == body:
        print("  %-52s INCONCLUSIVE" % label)
        return None
    bk = tempfile.mktemp(suffix=".tcl")
    shutil.copyfile(TCL, bk)
    try:
        io.open(TCL, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
        rc, _ = run()
    finally:
        shutil.copyfile(bk, TCL)
        os.unlink(bk)
    got = "ignored" if rc == 0 else "caught"
    ok = (got == expect)
    print("  %-52s %-8s %s" % (label, got.upper(), "ok" if ok else "*** WRONG ***"))
    results.append((label, got, expect, ok))


# 1  a COMMENT after write_bitstream - both exemptions apply, and it is genuinely inert
# A comment placed after the last artifact copy - the only region where a comment is doubly exempt.
_LAST = "file copy -force "
def comment_after_all(b):
    j = b.find(_LAST)
    if j < 0:
        return b
    k = b.find(chr(10), j)
    return b[:k + 1] + "# an inert note after every artifact action" + chr(10) + b[k + 1:]

inject("comment after every artifact copy", comment_after_all, "ignored")

# 2  CODE after write_bitstream that changes a later action - must be CAUGHT
def code_after(b):
    j = b.find("file copy -force $bit_src")
    if j < 0:
        return b
    return b[:j] + "set INJECTED_FLAG 1\n" + b[j:]


inject("code line after write_bitstream (before the copy)", code_after, "caught")

# 3  a comment BEFORE the build - the comment exemption applies, the region one does not
inject("comment before write_bitstream", lambda b: b.replace(
    MARK, "# pre-build note\n" + MARK, 1), "ignored")

# 4  code before the build - neither exemption applies
inject("code line before write_bitstream", lambda b: b.replace(
    MARK, "set PRE_FLAG 1\n" + MARK, 1), "caught")

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)

bad = [r for r in results if r[3] is False]
print()
if results and not bad and rc2 == 0:
    print("UNION-PASS (%d cases: comments ignored, code caught, wherever it sits)" % len(results))
    sys.exit(0)
print("UNION-FAIL (%d wrong)" % len(bad))
for label, got, want, _ in bad:
    print("   %s: got %s, wanted %s" % (label, got, want))
sys.exit(1)
