"""Are the report's quoted figures EXACTLY the numbers in the archives, at the point of the claim?

`check_traceability` asks whether each number has SOME archived record. It does not ask whether the digits match.

The first version of this check asked only "does 43428 appear somewhere in the report and somewhere in the archive" -
which passed even after the report's own claim was changed to 43438, because 43,428 appears several times in the
report. **A number that exists anywhere is not a number that is right.**

So each figure is anchored to the claim that uses it: the report must state `rx_messages=NNNNN` with the archived
value, and the archive must carry `rx_messages=NNNNN`.
"""
import glob
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
MEAS = os.path.join(REPO, "docs", "measurements")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

raw = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Historical board output sits in blockquotes and code fences, recording runs that FAILED. Those are evidence of what
# happened, not claims about what the golden result is. Round 27: `level_cnt=94` in the round-133 quotation was read
# as a current claim.
lines = []
in_fence = False
for line in raw.split("\n"):
    if line.lstrip().startswith("```"):
        in_fence = not in_fence
        continue
    if in_fence or line.lstrip().startswith(">"):
        continue
    lines.append(line)
text = "\n".join(lines)

# name -> (report claim pattern, archive label, archive families)
# Only the figures the report states as an explicit `key=value` claim outside a quotation.
# `order_cnt` and `level_cnt` appear as `order_cnt=` only inside blockquoted historical output, which is excluded -
# so they have no prose claim to anchor to and are not listed here. Round 27 tested that and said so rather than
# loosening the pattern until it matched something.
CLAIMS = [
    ("rx_packets",   r"rx_packets=(\d{2,4})",  "rx_packets",   ["board-recover", "k2-board-replay"]),
    ("rx_messages",  r"rx_messages=(\d{4,6})", "rx_messages",  ["board-recover", "k2-board-replay"]),
    ("parse_cnt",    r"parse_cnt=(\d{4,6})",   "parse_cnt",    ["board-recover"]),
]


def archive_claims(families, label):
    """Every value the archives assign to `label=`."""
    vals = set()
    for fam in families:
        for p in glob.glob(os.path.join(MEAS, "%s*" % fam)):
            s = io.open(p, encoding="utf-8", errors="replace").read().replace(",", "")
            vals.update(re.findall(r"%s=(\d+)" % re.escape(label), s))
    return vals


print("%-13s %-12s %-22s %s" % ("figure", "report says", "archives say", "verdict"))
print("-" * 72)

fails = []
for name, pat, label, families in CLAIMS:
    found = re.findall(pat, text.replace(",", ""))
    if not found:
        print("%-13s %-12s %-22s *** the report makes no such claim ***" % (name, "-", "-"))
        fails.append("%s: no claim in the report" % name)
        continue
    # The claim may be repeated; every stated value must be one the archives support.
    arch = archive_claims(families, label)
    stated = sorted(set(found))
    bad = [v for v in stated if v not in arch]
    verdict = "match" if not bad else "*** not in the archives: %s ***" % ", ".join(bad)
    print("%-13s %-12s %-22s %s"
          % (name, ",".join(stated[:3]) + ("..." if len(stated) > 3 else ""),
             ",".join(sorted(arch)[:3]) + ("..." if len(arch) > 3 else ""), verdict))
    if bad:
        fails.append(name)

print()
if fails:
    print("DIGIT-MATCH-FAIL (%s)" % "; ".join(fails))
    sys.exit(1)
print("DIGIT-MATCH-PASS (every golden figure the report states is one the archives record)")
