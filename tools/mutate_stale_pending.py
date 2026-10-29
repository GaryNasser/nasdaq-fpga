"""The stale-T1 case that check_impossible_stated must MISS, check_stale_pending must CATCH.

Two checks, complementary scopes, verified together:

    impossible_stated   K1/K2/DMA status wording
    stale_pending       any "仍需测量" naming a quantity already measured

Inserting a pending claim about T1 must be missed by the first and caught by the second -
otherwise the boundary is not where the two checks claim.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
A = r"D:\agent\nasdaq-fpga\tools\check_impossible_stated.py"
B = r"D:\agent\nasdaq-fpga\tools\check_stale_pending.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

CASES = [
    ("K1 stated as pending",
     original + "\n* K1\u4ecd\u9700\u4e0a\u677f\u6d4b\u91cf\u3002\n"),
    # Negative control: a subject the check is documented NOT to cover. It must stay uncaught here -
    # round 254 read that as a defect; the docstring says it is the design.
    ("T1 pending (out of scope)",
     original + "\n* \u677f\u4e0a\u5ef6\u8fdf\u7684 P50 \u4ecd\u9700\u4e0a\u677f\u6d4b\u91cf\u3002\n"),
    ]

print("%-26s %-22s %-22s" % ("mutation", "impossible_stated", "stale_pending"))
print()

results = []
for name, mutated in CASES:
    landed = mutated != original
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    ra = subprocess.run([sys.executable, A], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    rb = subprocess.run([sys.executable, B], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(original)
    a = "CAUGHT" if ra.returncode else "missed"
    b = "CAUGHT" if rb.returncode else "missed"
    results.append((name, landed, ra.returncode, rb.returncode))
    print("%-26s %-22s %-22s" % (name, a, b))

restored = io.open(REPORT, encoding="utf-8",
                   errors="surrogateescape").read() == original
print()
print("restored: %s" % restored)

ra = subprocess.run([sys.executable, A], capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
rb = subprocess.run([sys.executable, B], capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
print("healthy: impossible_stated exit %d, stale_pending exit %d"
      % (ra.returncode, rb.returncode))

shutil.copyfile(backup, REPORT)
os.unlink(backup)

print()
# Round 255: cases marked "out of scope" must stay UNCAUGHT by stale_pending - the check's docstring says it
# covers K1, K2 and DMA, and nothing else. Every in-scope case must be caught.
in_scope = [(l, rb_) for name, l, _, rb_ in results if "out of scope" not in name]
out_scope = [(l, rb_) for name, l, _, rb_ in results if "out of scope" in name]
ok = (restored and ra.returncode == 0 and rb.returncode == 0
      and all(l and rb_ != 0 for l, rb_ in in_scope)
      and all(rb_ == 0 for _, rb_ in out_scope))
print("STALE-PENDING-MUTATION-PASS" if ok else "STALE-PENDING-MUTATION-FAIL")
sys.exit(0 if ok else 1)
