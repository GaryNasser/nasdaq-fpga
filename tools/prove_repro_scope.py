"""Prove the round-244 relaxation cannot hide a design change.

`check_bit_repro` now ignores a change to a `.tcl` build script when it falls entirely AFTER
`launch_runs impl_1`. That is correct for a `puts`, and **wrong if it ever excuses an RTL edit**.

Two injections:

    1  a post-build `puts` in build_overlay.tcl          must stay IGNORED (the intended case)
    2  a change BEFORE write_bitstream in the same file  must be CAUGHT
    3  an RTL edit                                       must be CAUGHT
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_bit_repro.py")
TCL = os.path.join(REPO, "vivado", "build_overlay.tcl")
RTL = os.path.join(REPO, "rtl", "itch", "ts_hist.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=900)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("REPRO-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

results = []


def inject(label, path, transform, expect):
    body = io.open(path, encoding="utf-8", errors="surrogateescape").read() \
        if not path.endswith(".v") else io.open(path, encoding="latin-1").read()
    mutated = transform(body)
    if mutated == body:
        print("  %-44s INCONCLUSIVE" % label)
        results.append((label, None, expect))
        return
    bk = tempfile.mktemp(suffix=os.path.splitext(path)[1])
    shutil.copyfile(path, bk)
    try:
        enc = "latin-1" if path.endswith(".v") else "utf-8"
        mode = "a" if False else "w"
        io.open(path, "w", encoding=enc, errors="surrogateescape", newline="\n").write(mutated)
        rc, _ = run()
    finally:
        shutil.copyfile(bk, path)
        os.unlink(bk)
    result = "ignored" if rc == 0 else "caught"
    ok = (result == expect)
    print("  %-44s %-8s %s" % (label, result.upper(),
                               "as expected" if ok else "*** WRONG ***"))
    results.append((label, result, expect))


# 1  post-build puts: must be ignored
inject("post-build puts in build_overlay.tcl", TCL,
       lambda b: b.replace("close_project", 'puts "POST-GEN-NOTE"\nclose_project', 1)
       if "close_project" in b else b + '\nputs "POST-GEN-NOTE"\n', "ignored")

# 2  a change before write_bitstream: must be caught
def pre_build(b):
    marker = "launch_runs impl_1"
    i = b.find(marker)
    if i < 0:
        return b
    # A real CODE change before write_bitstream, not a comment: round 245 added a comment exemption,
    # so a comment injected here is now legitimately ignored. The boundary this proves is about code.
    return b[:i] + "set PRE_BUILD_CHANGE 1\n" + b[i:]


inject("code line before write_bitstream", TCL, pre_build, "caught")

# 3  an RTL edit: must be caught
inject("RTL edit", RTL, lambda b: b.replace("endmodule", "  // RTL-CHANGE\nendmodule", 1), "caught")

# 4  a comment-only edit must be IGNORED (round 245's exemption). A comment cannot change what Vivado builds.
COMMENT_MARK = "launch_runs impl_1"
inject("comment-only edit before the build", TCL,
       lambda b: b.replace(COMMENT_MARK,
                           "# a note that cannot change the build\n" + COMMENT_MARK, 1),
       "ignored")

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)

bad = [r for r in results if r[1] is not None and r[1] != r[2]]
print()
if not bad and rc2 == 0:
    print("REPRO-PROOF-PASS (the relaxation ignores only post-build edits and catches real ones)")
    sys.exit(0)
print("REPRO-PROOF-FAIL (%d wrong)" % len(bad))
for label, got, want in bad:
    print("   %s: got %s, wanted %s" % (label, got, want))
sys.exit(1)
