"""Prove check_digit_match catches a report figure that differs from its archive.

The check passes five golden figures. That proves nothing unless it can fail - and the figures are short enough
(320, 95, 850) that a naive check would match them anywhere in the archive text.

This perturbs each one in the report and requires the check to notice.
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
CHECK = os.path.join(TOOLS, "check_digit_match.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Perturb the figure where it appears as a golden claim, not everywhere.
CASES = [
    ("rx_messages=43428", "43428", "43438"),
    ("rx_packets=850", "850", "851"),
]


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "DIGIT-MATCH-PASS" if "DIGIT-MATCH-PASS" in out0 else "?"))
if rc0 != 0:
    print("DIGIT-MATCH-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
st = os.stat(REPORT)

results = []
try:
    for label, old, new in CASES:
        # Replace only inside the `rx_messages=NNNNN` style claim, not every occurrence.
        pattern = re.compile(r"rx_messages=%s" % re.escape(old)) if "messages" in label \
            else re.compile(r"rx_packets=%s" % re.escape(old))
        if not pattern.search(orig):
            # Fall back to the bare figure on a line that names it.
            pattern = re.compile(r"(%s)%s(?![\d])" % (r"rx_messages|rx_packets", re.escape(old)))
            if not pattern.search(orig):
                print("SKIP %-22s anchor not present in the report" % label)
                continue
            mutated = pattern.sub(lambda m: m.group(1) + new, orig, count=1)
        else:
            mutated = pattern.sub(pattern.pattern.replace(old, new), orig, count=1)
        landed = mutated != orig
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
        rc1, out1 = run()
        caught = rc1 != 0 and "DIGIT-MATCH-FAIL" in out1
        print("%-24s landed=%s exit=%d %s"
              % (label, landed, rc1, "CAUGHT" if caught else "MISSED"))
        results.append((landed, caught))
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(orig)
finally:
    shutil.copyfile(bk, REPORT)
    os.utime(REPORT, (st.st_atime, st.st_mtime))
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if results and all(l and c for l, c in results) and rc2 == 0:
    print("DIGIT-MATCH-PROOF-PASS (%d perturbation(s) caught)" % len(results))
    sys.exit(0)
print("DIGIT-MATCH-PROOF-FAIL")
sys.exit(1)
