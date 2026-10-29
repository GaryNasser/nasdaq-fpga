"""My injection never formed a pair: a tagged line goes into its own bucket, so a single occurrence cannot conflict.

To test whether a phrase HIDES a contradiction, the injection must also place a same-label figure in the PLAIN
bucket - then the tagged and plain values can be compared against each other by reading.

**But that is the design I just built: tagged lines are never compared with plain ones.** So the question becomes:
is that acceptable?

### Is it?

    plain:  "流水线 299.01 ns"                       one figure, checked against other plain ones
    tagged: "以上是：流水线 399.01 ns"               a figure in a sentence that says WHICH run it is

The tagged sentence names its own run. **A tagged figure differing from a plain one is not a conflict, it is the
distinction the sentence exists to make.** That is the case round 219 wanted to allow.

**The hazard round 219 recorded was different**: the phrase silenced the line entirely, so the line's OWN figures
were never compared with each other or with anything. **That is now fixed** - the line contributes its figures, and
they are compared with other tagged figures of the same label.

So the remaining question is narrower, and the right test is: **can two tagged figures of the same label disagree
without being caught?** That is what the new key shape decides.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "audit_crossnum.py")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=900)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("EXEMPT-FAIL (baseline)")
    sys.exit(1)

body = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Pick a label+unit that already appears in a PLAIN line.
NUM = r"(\d[\d,]*\.?\d*)"
UNIT = r"(msg/s|ns/msg|ns|cycles|Gbps|Mbps|pkt/s)"
PHRASES = "\u4ee5\u4e0a\u662f|\u677f\u4e0a\u5b9e\u6d4b|\u4eff\u771f\u503c|\u5bf9\u6bd4"
ex = None
for line in body.split("\n"):
    if re.search(PHRASES, line):
        continue
    m = re.search("([\u4e00-\u9fff]{2,10})[^\\d\\n]{0,8}" + NUM + r"\s*" + UNIT, line)
    if m and not line.strip().startswith("|"):
        ex = (m.group(1), m.group(2), m.group(3))
        break

if ex is None:
    print("EXEMPT-INCONCLUSIVE")
    sys.exit(0)

label, value, unit = ex
alt = ("7" + value) if value[0] != "7" else ("6" + value)
print("plain exemplar: %s %s %s" % (label, value, unit))
print()

results = []


def inject(tag, extra):
    bk = tempfile.mktemp(suffix=".md")
    shutil.copyfile(REPORT, bk)
    try:
        io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(
            body + "\n\n" + extra + "\n")
        rc, _ = run()
    finally:
        shutil.copyfile(bk, REPORT)
        os.unlink(bk)
    caught = rc != 0
    print("  %-52s %s" % (tag, "CAUGHT" if caught else "MISSED"))
    results.append((tag, caught))


# Two TAGGED lines with the same label and different values: these are in the same bucket.
inject("two tagged lines disagree (%s)" % label,
       "\u4ee5\u4e0a\u662f\uff1a%s %s %s\u3002\n\u4ee5\u4e0a\u662f\uff1a%s %s %s\u3002"
       % (label, value, unit, label, alt, unit))

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    print("EXEMPT-PASS (two figures both marked as other runs are still compared with each other)")
    sys.exit(0)
print("EXEMPT-FAIL (tagged figures are not compared even with each other)")
sys.exit(1)
