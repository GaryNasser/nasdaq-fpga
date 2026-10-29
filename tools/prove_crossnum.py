"""Prove audit_crossnum fails on a duplicated figure with a matching label.

Round 220 established that the audit only compares a figure whose label sits on the SAME line, and that it sees
41 of 121. **Whether it catches a contradiction among those 41 has never been tested.**

Inject a line whose label and unit match an existing figure but whose value differs, and confirm exit 1.
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
AUDIT = os.path.join(REPO, "tools", "audit_crossnum.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, AUDIT], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(AUDIT), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("CROSSNUM-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Find a figure the audit DOES compare: label and unit on one line.
NUM = r"(\d[\d,]*\.?\d*)"
# Round 12: "ns" was listed BEFORE "ns/msg", so the regex grabbed the shorter unit and the injected
# claim used a different unit than the original - the audit correctly did not see a contradiction, and
# the proof reported MISSED against itself. Longest alternatives must come first.
UNIT = r"(ns/消息|ns/msg|msg/s|cycles|Gbps|Mbps|pkt/s|ns)"
ex = None
for line in body.split("\n"):
    m = re.search("([\u4e00-\u9fff]{2,8})[^\\d\\n]{0,4}" + NUM + r"\s*" + UNIT, line)
    # Round 12: require a SHORT label with the number adjacent. A long sentence puts other Chinese words
    # between the label and the figure, and audit_crossnum then does not key them together - so the
    # injected contradiction landed on a label the audit never compares.
    if m and not line.strip().startswith(("|", ">")) and len(line) < 160:
        ex = (m.group(1), m.group(2), m.group(3), line.strip()[:50])
        break

if ex is None:
    print("CROSSNUM-PROOF-INCONCLUSIVE (no same-line labelled figure to duplicate)")
    sys.exit(0)

label, value, unit, ctx = ex
print("exemplar: %s %s %s   (from: %s)" % (label, value, unit, ctx))

# A different value, same magnitude shape.
alt = value.replace(value[0], str((int(value[0]) + 1) % 10), 1) if value[0].isdigit() else "9" + value
if alt == value:
    alt = "9" + value

bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(
        body + "\n\n%s %s %s\u3002\n" % (label, alt, unit))
    rc1, out1 = run()
    caught = rc1 != 0
    print("injected: %s %s %s" % (label, alt, unit))
    print("mutated : exit=%d %s" % (rc1, "CAUGHT" if caught else "MISSED"))
    if not caught:
        for l in [x for x in out1.split("\n") if x.strip()][:5]:
            print("   " + l.strip()[:80])
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if caught and rc2 == 0:
    print("CROSSNUM-PROOF-PASS (a duplicated labelled figure is caught)")
    sys.exit(0)
print("CROSSNUM-PROOF-FAIL")
sys.exit(1)
