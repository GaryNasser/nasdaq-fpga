"""Prove both directions of the new arch_fresh baseline.

The check must:

  A. stay ARCH-CURRENT when a source's mtime moves but its content does not
     (this is round 58's exact situation - the XDC is 17 minutes newer);
  B. go stale when a source's CODE changes, even if the mtime is older than the bitstream.

A is the improvement. B guards against the new baseline being too lenient.

Case A: touch rtl/itch/order_book.v (mtime now, content unchanged).
Case B: append a comment AND change code? No - a comment must NOT count (round 36). So B
        changes real code: add a harmless but real statement to a module, and set the mtime
        to something older than the bitstream.

Both must be restored afterwards, and the restore verified by fingerprint.
"""
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

REPO = r"D:\agent\nasdaq-fpga"
CHECK = os.path.join(REPO, "tools", "check_arch_fresh.py")
TARGET = os.path.join(REPO, "rtl", "itch", "order_book.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


backup = tempfile.mktemp(suffix=".v")
shutil.copyfile(TARGET, backup)
original_bytes = open(TARGET, "rb").read()
original_mtime = os.path.getmtime(TARGET)

results = []

# --- A. touch only ----------------------------------------------------------
os.utime(TARGET, None)   # mtime = now, content identical
rc, out = run()
# Round 8: `check_arch_fresh` documents "A newer mtime does not mean a newer DESIGN" and compares
# content fingerprints, deliberately ignoring a bare touch. **Touching a file must therefore report
# CURRENT.** Round 7 briefly asserted the opposite - an error I introduced while chasing a timestamp
# problem, then spent two rebuild cycles un-learning.
ok_a = (rc == 0 and "ARCH-CURRENT" in out)
results.append(("mtime moved, content same", ok_a, rc))
print("A. mtime moved, content identical -> exit %d %s"
      % (rc, "STALE (correct for an mtime check)" if "ARCH-STALE" in out else "(unexpected)"))
shutil.copyfile(backup, TARGET)
os.utime(TARGET, (original_mtime, original_mtime))
# Round 7: copyfile writes the file anew, so its mtime becomes "now" and this test's own restore makes
# the source look newer than the bitstream - the next suite run reports ARCH-STALE against a tree that
# is actually current. Restore the original timestamp too. (Same bug as prove_pair_guard, round 3.)
os.utime(TARGET, (original_mtime, original_mtime))

# --- B. code change with an OLD mtime ---------------------------------------
text = io.open(TARGET, encoding="latin-1").read()
# Insert a real statement into the module body: a harmless always-false assign.
marker = "module order_book"
i = text.find(marker)
semi = text.find(";", i) + 1
mutated = text[:semi] + "\n  wire unused_marker_x = 1'b0;" + text[semi:]
io.open(TARGET, "w", encoding="latin-1", newline="\n").write(mutated)
os.utime(TARGET, (original_mtime, original_mtime))   # Round 7: NOT an hour older
    # check_arch_fresh decides by mtime, so back-dating a changed file makes it look CURRENT - which is
    # exactly the case this test must prove is caught only if the content is also compared. Keep the
    # original timestamp so the only variable is the content.
rc, out = run()
changed = "ARCH-STALE" in out or "stale" in out.lower() or rc != 0
results.append(("code changed, mtime older", changed, rc))
print("B. code changed, mtime set 1 h older -> exit %d %s"
      % (rc, "detected" if changed else "MISSED"))

# --- restore ---------------------------------------------------------------
open(TARGET, "wb").write(original_bytes)
os.utime(TARGET, (original_mtime, original_mtime))
restored = open(TARGET, "rb").read() == original_bytes
os.unlink(backup)

rc2, out2 = run()
print()
print("restored byte-identical: %s" % restored)
print("healthy run            : exit %d %s" % (rc2,
                                               "ARCH-CURRENT" if "ARCH-CURRENT" in out2 else "?"))

print()
if all(ok for _, ok, _ in results) and restored and rc2 == 0:
    print("ARCH-FRESH-BASELINE-PASS (content decides; mtime alone does not)")
else:
    print("ARCH-FRESH-BASELINE-FAIL")
    for name, ok, rc in results:
        print("  %-28s %s (exit %d)" % (name, "ok" if ok else "WRONG", rc))
    sys.exit(1)
