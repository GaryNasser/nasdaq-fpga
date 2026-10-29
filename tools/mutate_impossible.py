"""Finish mutate_impossible.py so the stale-T1 case asserts MISS rather than failing.

Three mutations, two of which this check must catch:

    restore 仍需上板          CAUGHT
    restore 尚未实测 list     CAUGHT
    add a stale T1 pending    MISSED - by design, since it names no K1/K2/DMA. Its coverage
                              lives in check_stale_pending, and this harness records that
                              the boundary is where I think it is.

The verdict requires the two actionable mutations caught, the boundary case missed, the
document restored, and the healthy path passing.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_impossible_stated.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

CASES = []

m1 = original.replace(
    "* K1（千兆线速不丢包）与 K2（网线到建簿）**不是「尚未做」，而是这台板做不了**",
    "* K1（千兆线速不丢包）与 K2（网线到建簿）仍需上板", 1)
if m1 != original:
    CASES.append(("restore 仍需上板", m1, True))

m2 = original.replace("**三项拿不到，且各有各的原因**：", "尚未实测：", 1)
if m2 != original:
    CASES.append(("restore 尚未实测 list", m2, True))

m3 = original + "\n* 板上延迟分布的 P50/P95/P99 仍需上板测量。\n"
CASES.append(("stale T1 pending (out of scope)", m3, False))

if not CASES:
    print("could not build mutations")
    sys.exit(2)

results = []
for name, mutated, should_catch in CASES:
    landed = mutated != original
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught, should_catch))
    verdict = "CAUGHT" if caught else "missed"
    want = "expected CAUGHT" if should_catch else "expected missed"
    ok = caught == should_catch
    print("%-32s landed=%-5s exit=%d %-7s (%s) %s"
          % (name, landed, r.returncode, verdict, want, "ok" if ok else "WRONG"))
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(original)

restored = io.open(REPORT, encoding="utf-8",
                   errors="surrogateescape").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, REPORT)
os.unlink(backup)

print()
ok = (all(l and c == w for _, l, c, w in results) and restored
      and r.returncode == 0)
print("IMPOSSIBLE-STATED-MUTATION-PASS" if ok else "IMPOSSIBLE-STATED-MUTATION-FAIL")
sys.exit(0 if ok else 1)
