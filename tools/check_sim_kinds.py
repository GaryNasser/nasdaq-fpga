"""Assert that every suite declares what its pass token MEANS.

`coldstart` passes when `COLD-FAIL` appears: the test demonstrates that a bad sequence
still corrupts the stream, so observing the failure is the pass condition. In the log
that looked identical to a broken suite.

Round 27's hardened verdict made this fragile. It requires "no Fatal:/ERROR: line", so
adding `$fatal` to tb_cold_start - an obvious way to make a failing test clearer -
would have made a correct suite report FAIL, for a reason nobody would connect to the
edit.

SUITES now carries a `kind` field per suite and the runner uses it. This check keeps
the declaration honest:

  * every SUITES entry has a kind of KIND_PASS or KIND_EXPECTED - no entry may omit
    it, or the runner raises at unpack time;
  * any suite whose token contains FAIL is declared KIND_EXPECTED, so a suite whose
    pass condition is a failure word can never be mistaken for a broken one;
  * conversely, a KIND_EXPECTED suite whose token says PASS is suspicious, because
    the "expected failure" rule exists to tolerate failures.

The third rule is a smell test rather than an error: printing it makes a mismatch
visible at a glance.
"""
import io
import re
import sys

PATH = r"D:\agent\nasdaq-fpga\tools\run_sims.py"
src = io.open(PATH, encoding="utf-8").read()

lines = src.split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("SUITES"))
end = next(i for i in range(start + 1, len(lines))
           if lines[i].rstrip().endswith("]"))

fails = []
rows = 0
print("%-12s %-24s %s" % ("suite", "token", "kind"))
print("-" * 62)

for i in range(start + 1, end):
    line = lines[i].strip()
    if not line.startswith('("'):
        continue
    rows += 1
    m = re.match(r'\("(\w+)"', line)
    suite = m.group(1) if m else "?"
    t = re.search(r'"([A-Z][A-Z0-9-]+)"', line)
    token = t.group(1) if t else "?"
    k = re.search(r"(KIND_\w+)", line)
    kind = k.group(1) if k else "MISSING"

    note = ""
    if kind == "MISSING":
        note = "no kind declared"
        fails.append("%s: kind missing" % suite)
    elif "FAIL" in token and kind != "KIND_EXPECTED":
        note = "token says FAIL but kind says pass"
        fails.append("%s: %s token with %s" % (suite, token, kind))
    elif "FAIL" not in token and kind == "KIND_EXPECTED":
        note = "expected-failure kind on a PASS token"
        fails.append("%s: KIND_EXPECTED on %s" % (suite, token))

    print("%-12s %-24s %-16s %s" % (suite, token, kind, note))

print()
print("%d suite(s) examined" % rows)
if rows == 0:
    print("SIM-KIND-FAIL (no suites parsed)")
    sys.exit(1)
if fails:
    print("SIM-KIND-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("SIM-KIND-PASS")
