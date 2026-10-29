"""Every figure the report calls 实测 must appear in a board measurement record.

Three rounds, three faults of one family:

    round 76   93.6 MB/s   computed from a rounded input, quoted as exact
    round 77   94 MB/s     a simulation labelled 实测
    round 78   615 MB/s    a measurement that was never made

Each was invisible to reading. The common property that makes them checkable: a figure
labelled as measured must appear somewhere in the board's own output - the defect log's run
records, docs/measurements/, or the driver's golden values.

This check extracts every figure from a sentence carrying a 实测 label, and requires that it
be traceable. Numbers that are not quantities (dates, register addresses, part numbers) are
skipped by requiring the figure to be adjacent to a unit or a known metric name.

Exemptions are listed explicitly: the 实测 label on an environment description, or on a
statement about what was NOT measured, is not a measurement claim.
"""
import glob
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
LOG = os.path.join(REPO, "docs", "bringup-defects.md")
MEAS = os.path.join(REPO, "docs", "measurements")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(REPORT):
    print("MEASURED-TRACE-FAIL (no report)")
    sys.exit(1)

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Evidence means RECORD LINES, not any occurrence. A number that appears only in prose -
# including the prose that corrects an earlier claim about it - has not been measured.
# The shapes a measurement record actually takes in this repository, gathered from the
# log rather than imagined:
#     | **p50** | 40 | **210.5** |        table rows
#     T1 latency   p50 210.5 ns, ...      label then values
#     throughput   2,230,335 msg/s        word then value
#     RATE evt=43428 span_cycles=...      the testbench printout
KEYVAL = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\s*[=:]\s*\S")   # case-sensitive: REAL_KEY=value
# RATE is a testbench token printed in upper case only. Matching it case-insensitively made
# the ordinary word "rate" in prose satisfy the record test, which is how a sentence
# asserting an unmeasured 615 MB/s passed as evidence.
RATE_TOKEN = re.compile(r"\bRATE\b")
WORDS = re.compile(
    r"^\s*\|"                                    # a markdown table row
    r"|\bp50\b|\bp95\b|\bp99\b"              # percentile labels, either case
    r"|throughput|samples|overflow"
    r"|span_cycles|evt=|ns_per_msg|msg_per_s",
    re.I)


# A line that says a figure was NEVER measured is not evidence that it was. The defect log is full of
# them - "615 appears twice ... never measured" - and treating those as records would let the very
# number the check exists to catch be evidenced by the note explaining it is fake. (Round 4.)
NOT_EVIDENCE = re.compile(
    r"从未|never|不成立|撤回|withdrawn|不是实测|not measured|fake|虚构|\u6d4b\u91cf\u4e0d\u5b58\u5728|"
    r"\u6ca1\u6709\u5b9e\u6d4b|\u672a\u5b9e\u6d4b|\u65e0\u5b9e\u6d4b|"
    # A transcription of a mutation proof's output is not a measurement record. The log quotes
    # lines like `alter P50 210.5 -> 212.7  landed=True exit=1 CAUGHT`, which would otherwise make
    # 212.7 look recorded. (Round 4.)
    r"landed=|MUTATION-PASS|MUTATION-FAIL|CAUGHT|MISSED")


def is_record(ln):
    """A record line pairs a label with a value; prose does not."""
    if NOT_EVIDENCE.search(ln):
        return False
    if WORDS.search(ln) or RATE_TOKEN.search(ln):
        return True
    return bool(KEYVAL.search(ln))


evidence_lines = []
for p in [LOG] + sorted(glob.glob(os.path.join(MEAS, "*"))):
    if not os.path.exists(p):
        continue
    for ln in io.open(p, encoding="utf-8", errors="replace").read().split("\n"):
        # A line that names the number the check is ABOUT - "615 appears twice, never measured",
        # "`615` 命中 `2203615`" - is documentation of the fault, not evidence of a measurement.
        # Strip such mentions before deciding whether the line is a record.
        if re.search(r"(?<![\d.])615(?![\d])", ln):
            continue
        if is_record(ln):
            evidence_lines.append(ln)
evidence = "\n".join(evidence_lines)

# A quantity with a unit, on a line that claims measurement.
QUANTITY = re.compile(
    r"(?<![\d.])(\d[\d,]*(?:\.\d+)?)\s*"
    r"(ns|µs|us|ms|MB/s|GB/s|个样本|samples|包|条消息|消息/秒|msg/s)")

CLAIM = re.compile(r"板上实测|板上已实测|实测的|已实测")

# Quantities that legitimately sit on a 实测 line without being measured themselves.
# Listed explicitly, so an addition is a deliberate act rather than a regex side effect.
NOT_MEASURED_HERE = {
    "190": "byte-port arithmetic: 1 B/cycle at 190 MHz",
    "94.5": "simulated pipeline rate, quoted as a comparison",
    "299.01": "simulated ns/message, quoted as a comparison",
    "0.50": "ratio derived from measured rates",
    "1.52": "ratio derived from the byte-port figure",
    "63.0": "board data rate DERIVED from the measured 2,230,335 msg/s x 28.252 B",
    "63": "same, rounded",
}

print("measured figures and whether a board record contains them")
print()

missing = []
checked = 0
for i, line in enumerate(text.split("\n"), 1):
    if not CLAIM.search(line):
        continue
    for m in QUANTITY.finditer(line):
        value = m.group(1)
        unit = m.group(2)
        checked += 1
        if value in NOT_MEASURED_HERE:
            print("  L%-5d %-10s %-6s  %s"
                  % (i, value, unit, NOT_MEASURED_HERE[value][:52]))
            continue
        # 1.52x / 0.50x are ratios derived from measured rates - allowed.
        # Round 3: a plain substring test let "615" match "2203615 msg/s" in an archived
        # record, so a reintroduced 615 MB/s claim passed as evidenced. Require the value to
        # appear as a whole number, not as part of a longer one.
        def norm(s):
            return s.replace(",", "")

        pat = r"(?<![\d.])" + re.escape(norm(value)) + r"(?![\d.])"
        ok = re.search(pat, norm(evidence)) is not None
        print("  L%-5d %-10s %-6s  record: %s"
              % (i, value, unit, "yes" if ok else "*** NO ***"))
        if not ok:
            missing.append((i, value + " " + unit, line.strip()))

print()
print()
print("  %d evidence line(s) that look like tool records" % len(evidence_lines))
print("  %d measured figure(s) checked" % checked)

if missing:
    print()
    print("MEASURED-TRACE-FAIL (%d)" % len(missing))
    for i, v, line in missing:
        print("  L%d: %s has no board record" % (i, v))
        print("     %s" % line[:96])
    sys.exit(1)
if checked == 0:
    print()
    print("MEASURED-TRACE-FAIL (no measured figures found - the scan would be vacuous)")
    sys.exit(1)
print()
print("MEASURED-TRACE-PASS (every 实测 figure has a board record)")
