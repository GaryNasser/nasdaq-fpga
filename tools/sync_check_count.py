"""Set the reproduction section's check count from run_checks.py itself.

The section has drifted twice: round 16 wrote 27 for the "N 项" prose while the
sample count line was updated separately, and rounds 17-21 bumped the sample line
without touching the prose. Two numbers describing the same thing, edited
independently, is how they disagree.

This reads the actual count from CHECKS and writes BOTH places, so they cannot
diverge.
"""
import io
import re

REPO = r"D:\agent\nasdaq-fpga"
RC = REPO + r"\tools\run_checks.py"
DOC = REPO + r"\docs\final-report.md"

rc = io.open(RC, encoding="utf-8").read()
lines = rc.split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("CHECKS"))
end = next(i for i in range(start + 1, len(lines))
           if lines[i].rstrip().endswith("]")
           and not lines[i].lstrip().startswith("("))
seg = "\n".join(lines[start:end])
n = len(re.findall(r"\(\s*\"\w+\",", seg))
print("checks in run_checks.py: %d" % n)

doc = io.open(DOC, encoding="utf-8", errors="surrogateescape").read()

# The prose count: "**N 项**独立检查"
before = doc
doc = re.sub(r"\*\*\d+ 项\*\*独立检查", "**%d 项**独立检查" % n, doc, count=1)
prose_changed = doc != before

# The sample output line
before = doc
doc = re.sub(r"passed \d+, failed 0, skipped 0 of \d+",
             "passed %d, failed 0, skipped 0 of %d" % (n, n), doc, count=1)
sample_changed = doc != before

io.open(DOC, "wb").write(doc.encode("utf-8", errors="surrogateescape"))
print("prose updated: %s, sample line updated: %s"
      % (prose_changed, sample_changed))
