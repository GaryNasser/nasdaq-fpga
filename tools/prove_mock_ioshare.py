"""Prove mock_run and io_share can fail - restored with landed-checks.

I deleted the original script after registering it in run_checks.py, and the suite correctly
failed on the dangling entry. Restored under a new name with what round 94's audit found
missing: an explicit confirmation that each mutation changed its target.

    mock_run    change an expected token GOLDEN-OK -> XX
    io_share    point SRC at a file that cannot compile
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
MOCK = os.path.join(TOOLS, "mock_run.py")
IOS = os.path.join(TOOLS, "measure_io_share.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run(check):
    try:
        r = subprocess.run([sys.executable, os.path.join(TOOLS, check)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    return r.returncode, (r.stdout or "") + (r.stderr or "")


results = []

# --- mock_run: an expected token the driver never prints --------------------
src = io.open(MOCK, encoding="utf-8").read()
anchor = '"GOLDEN-OK")'
i = src.find(anchor)
if i == -1:
    print("MOCK-IOSHARE-PROOF-FAIL (GOLDEN-OK anchor not found)")
    sys.exit(1)
mutated = src[:i] + '"GOLDEN-OK-XX")' + src[i + len(anchor):]
landed = mutated != src
print("mock_run mutation landed : %s" % landed)
if not landed:
    print("MOCK-IOSHARE-PROOF-FAIL (mutation did not land)")
    sys.exit(1)

bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(MOCK, bk)
try:
    io.open(MOCK, "w", encoding="utf-8", newline="\n").write(mutated)
    rc, out = run("mock_run.py")
    caught = rc != 0
    results.append(("mock_run", landed, caught))
    print("   exit=%d %s" % (rc, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, MOCK)
    os.unlink(bk)

# --- io_share: a source file that cannot compile ---------------------------
src = io.open(IOS, encoding="utf-8").read()
m = re.search(r'SRC\s*=\s*os\.path\.join\(REPO,[^\n]*\)', src)
if not m:
    print("MOCK-IOSHARE-PROOF-FAIL (io_share SRC anchor not found)")
    sys.exit(1)
mutated = src.replace(m.group(0), 'SRC = os.path.join(REPO, "docs", "no_such.c")', 1)
landed2 = mutated != src
print("io_share mutation landed : %s" % landed2)
if not landed2:
    print("MOCK-IOSHARE-PROOF-FAIL (mutation did not land)")
    sys.exit(1)

bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(IOS, bk)
try:
    io.open(IOS, "w", encoding="utf-8", newline="\n").write(mutated)
    rc, out = run("measure_io_share.py")
    caught2 = rc != 0
    results.append(("io_share", landed2, caught2))
    print("   exit=%d %s" % (rc, "CAUGHT" if caught2 else "MISSED"))
finally:
    shutil.copyfile(bk, IOS)
    os.unlink(bk)

print()
for c in ("mock_run.py", "measure_io_share.py"):
    rc, _ = run(c)
    print("  %-26s exit=%d (restored)" % (c, rc))

print()
if all(l and c for _, l, c in results):
    sys.exit(0)
print("MOCK-IOSHARE-PROOF-FAIL")
sys.exit(1)
