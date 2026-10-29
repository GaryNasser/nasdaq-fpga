"""Prove all three independent assertions in check_wns_ownership.

Read from the source first (rounds 230's lesson), the check fails when:

    L65  the shipped value +0.126 is not cited anywhere
    L67  the current-source value +0.042 is not cited anywhere
    L71  the rebuild value +0.157 appears ONLY in prose, with no table column attribution
    L90  the summary block is non-empty and does not quote the shipped value

Each is a separate code path, so each gets its own injection.

### Why these matter together

`+0.157` is the value a stale rebuild produced. It is legitimately owned by the timing table, where the column
header says which build each column is - **but if it drifts into prose, it becomes an unattributed claim the reader
will read as current.**
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHK = os.path.join(REPO, "tools", "check_wns_ownership.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, out0 = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("WNS-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
print()


def inject(label, transform):
    """Apply transform(text) -> text, run, restore."""
    bk = tempfile.mktemp(suffix=".md")
    shutil.copyfile(REPORT, bk)
    try:
        mutated = transform(body)
        if mutated == body:
            print("  %-34s INCONCLUSIVE (transform changed nothing)" % label)
            return None
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
        rc, out = run()
    finally:
        shutil.copyfile(bk, REPORT)
        os.unlink(bk)
    caught = rc != 0
    print("  %-34s exit=%-3d %s" % (label, rc, "CAUGHT" if caught else "MISSED"))
    return caught


results = []

# 1  Remove every citation of the shipped value.
results.append(("shipped value removed", inject(
    "shipped +0.126 removed",
    lambda t: t.replace("+0.126", "+0.999").replace("**0.126", "**0.999"))))

# 2  Remove every citation of the current-source value.
results.append(("current-source value removed", inject(
    "current +0.042 removed",
    lambda t: t.replace("+0.042", "+0.998").replace("0.042 ns", "0.998 ns"))))

# 3  Move the rebuild value into prose only: strip it from the table rows, add a prose sentence.
def prose_only(t):
    t2 = re.sub(r"(\|\s*WNS\s*\|[^\n]*?)\+\s*0\.157\s*ns", r"\1+0.996 ns", t)
    t2 = re.sub(r"(\|\s*WNS\s*\|[^\n]*?)0\.157", r"\g<1>0.996", t2)
    if t2.count("0.157") > 0 and "WNS +0.157" not in t2:
        t2 += "\n\nThe rebuild measured WNS +0.157 ns.\n"
    return t2


results.append(("rebuild value in prose only", inject("rebuild +0.157 prose only", prose_only)))

# 4  Make the summary quote a different value.
def summary_swap(t):
    head_end = t.find("\n## ")
    if head_end < 0:
        return t
    head, rest = t[:head_end], t[head_end:]
    return head.replace("+0.126", "+0.997") + rest


results.append(("summary quotes a stale value", inject("summary swapped", summary_swap)))

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)

caught = sum(1 for _, c in results if c)
total = sum(1 for _, c in results if c is not None)
print()
if total and caught == total and rc2 == 0:
    print("WNS-PROOF-PASS (%d/%d assertions caught)" % (caught, total))
    sys.exit(0)
print("WNS-PROOF-FAIL (%d of %d caught)" % (caught, total))
for label, c in results:
    if not c:
        print("   not caught: " + label)
sys.exit(1)
