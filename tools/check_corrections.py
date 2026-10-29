"""The conflict scan cannot tell a live figure from a correction record. Verify the records instead.

The report contains:

    93.6 MB/s   L654  "此前写 93.6 MB/s ... 应为 **94.5 MB/s**"        a record
    94   MB/s   L656  "此前把「实测端到端」写成 94 MB/s"                 a record
    94.5 MB/s   L529,649,655,657,1151                                 live
    63.0 MB/s   L22,529,649,651,652,657                               live

Grouping by unit reports these as "6 distinct values, possible staleness" - which is wrong.
They are two live values and three historical mentions, each labelled as such.

The property worth checking is the one round 100 found broken: **a correction record must be
internally consistent**. "此前写 X，应为 Y" is a claim that X was wrong and Y is right, and that
follows from the stated reason.

So: parse every correction record and verify
  * the old value differs from the new one (a record saying "from 33.3% to 33.3%" is nonsense)
  * the new value equals what the record's own reason implies, when the reason carries arithmetic
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
lines = text.split("\n")

print("correction records in the report")
print()

fails = []
# Forms: "此前写 X，应为 Y" / "由 X 变为 Y" / "此前把 A 写成 B"
RECORDS = [
    ("此前写 ... 应为", re.compile(r"此前写\s*([\d.]+)\s*([A-Za-z/]*)[\s\S]{0,80}?应为\s*\*{0,2}([\d.]+)")),
    ("由 X 变为 Y", re.compile(r"由\s*([\d.]+)\s*%?\s*变为\s*\*{0,2}([\d.]+)")),
]

count = 0
for label, rx in RECORDS:
    for m in rx.finditer(text):
        count += 1
        ln = text[:m.start()].count("\n") + 1
        groups = m.groups()
        old, new = groups[0], groups[-1]
        if old == new:
            fails.append((ln, "%s: '%s' 变为 '%s' - a record that changes nothing"
                          % (label, old, new)))
            print("  L%-5d %s  *** from %s to the same value ***" % (ln, label, old))
        else:
            print("  L%-5d %s  %s -> %s" % (ln, label, old, new))

print()
print("  records found: %d" % count)

# Round 100's specific case: the gap's reason is (94.5-63.0)/94.5.
# Read the two rates from the report so the arithmetic is not a second memory.
def _rate(pattern, what):
    m = re.search(pattern, text)
    if not m:
        print("  %-22s NOT FOUND" % what)
        return None
    return float(m.group(1))

sim = _rate(r"应为 \*\*(\d+\.\d+) MB/s\*\*", "simulated MB/s")
board = _rate(r"\*\*(\d+\.\d+) MB/s（0\.50× 1 GbE）\*\*", "board MB/s")
if sim is None or board is None:
    sys.exit(1)
expected_gap = (sim - board) / sim * 100
m = re.search(r"差额[^\n]*?\*\*(\d+\.\d+)%\*\*", text)
if m:
    stated = float(m.group(1))
    ok = abs(stated - expected_gap) < 0.15
    print()
    print("  live gap: stated %.1f%%, (%.1f-%.1f)/%.1f = %.2f%%  %s"
          % (stated, sim, board, sim, expected_gap, "ok" if ok else "MISMATCH"))
    print("  note: in this document the live gap IS the record's conclusion - both are")
    print("        the bolded 33.3 - so a wrong gap shows up as a broken record too.")
    if not ok:
        fails.append((0, "live gap %.1f%% != %.2f%%" % (stated, expected_gap)))

print()
if fails:
    print("CORRECTION-RECORD-FAIL (%d)" % len(fails))
    for ln, msg in fails:
        print("  L%d: %s" % (ln, msg))
    sys.exit(1)
print("CORRECTION-RECORD-PASS (every correction changes its value; the live gap follows)")
