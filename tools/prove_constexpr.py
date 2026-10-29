"""Prove check_constexpr catches a wrong constant - the exact defect it exists for.

The check evaluates RTL constants in xsim and compares against EXPECT. **The FIFO_BYTES bug is the reason it
exists**: the depth evaluated to 6144 instead of 4096, the ring overflowed, and ten isolated tests missed it.

### The mutation

Change the localparam expression in the RTL so FIFO_BYTES evaluates to a different number. The check must fail,
and the failure must NAME FIFO_BYTES - a check that fails for an unrelated reason (a compile error, a missing
file) proves nothing about its comparison.

That distinction is the point: **CAUGHT is necessary but not sufficient; it must be caught for the right reason.**
"""
import io
import os
import re
import shutil
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_constexpr.py")
SRC = os.path.join(REPO, "rtl", "itch", "mold64_reasm.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=900)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


if not os.path.exists(SRC):
    print("CONSTEXPR-PROOF-FAIL (no source to mutate)")
    sys.exit(1)

rc0, out0 = run()
print("baseline: exit=%d" % rc0)
if "CONSTEXPR-SKIPPED" in out0:
    print("CONSTEXPR-PROOF-FAIL (the baseline SKIPPED - xvlog missing, so nothing was proven)")
    sys.exit(1)
if rc0 != 0:
    print("CONSTEXPR-PROOF-FAIL (does not pass on the current tree)")
    for l in [x for x in out0.split("\n") if x.strip()][-3:]:
        print("   " + l.strip()[:80])
    sys.exit(1)

src = io.open(SRC, encoding="utf-8", errors="surrogateescape").read()
m = re.search(r"(localparam[^\n]*?FIFO_BYTES[^\n]*?=\s*)([^\n;]+)(;)", src)
if not m:
    print("CONSTEXPR-PROOF-FAIL (no FIFO_BYTES declaration found)")
    sys.exit(1)

print("declaration: %s" % m.group(0).strip()[:78])

bk = SRC + ".bak"
shutil.copyfile(SRC, bk)
try:
    mutated = src[:m.start(2)] + "8'd16" + src[m.end(2):]
    io.open(SRC, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
    print("mutated to : FIFO_BYTES = 8'd16")

    rc1, out1 = run()
    caught = rc1 != 0
    names_it = "FIFO_BYTES" in out1
    print("mutated : exit=%d %s%s" % (rc1, "CAUGHT" if caught else "MISSED",
                                      "" if names_it else "  (but does not name FIFO_BYTES)"))
    if not caught:
        for l in [x for x in out1.split("\n") if x.strip()][-3:]:
            print("   " + l.strip()[:80])
finally:
    shutil.copyfile(bk, SRC)
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)

print()
if caught and names_it and rc2 == 0:
    print("CONSTEXPR-PROOF-PASS (a wrong FIFO_BYTES is caught, and the failure names it)")
    sys.exit(0)
print("CONSTEXPR-PROOF-FAIL (caught=%s names_it=%s restored_clean=%s)"
      % (caught, names_it, rc2 == 0))
sys.exit(1)
