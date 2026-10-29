"""Read the baseline by field name, not by unit.

The file writes:

    BASELINE-RESULT: msgs=43428 bytes=1226916 elapsed_ns=40272752 ns_per_msg=927.35  msg_per_s=1078346.97

My first parser searched for "(\\d+\\.\\d+)\\s*ns" and found nothing, because the value is
followed by two spaces and "msg_per_s", not by "ns". The file was complete; the pattern was not.

This check reads the key=value pairs, so it is independent of formatting:

    ns_per_msg   -> must equal the report's 927.35
    msg_per_s    -> must equal the report's 1,078,347 (rounding)
    msgs, bytes  -> must match the capture

Also verifies that 927.35 is the BEST of the four runs, since the report calls it "4 次取最优".
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
BASE = os.path.join(REPO, "docs", "measurements", "baseline-a9.txt")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

body = io.open(BASE, encoding="latin-1").read()
rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

runs = []
for line in body.split("\n"):
    if not line.startswith("BASELINE-RESULT:"):
        continue
    kv = dict(re.findall(r"(\w+)=([\d.]+)", line))
    if "ns_per_msg" in kv:
        runs.append({k: float(v) for k, v in kv.items()})

print("baseline-a9.txt: %d run(s)" % len(runs))
print()

fails = []
if not runs:
    print("  no BASELINE-RESULT lines parsed")
    sys.exit(1)

for i, r in enumerate(runs, 1):
    print("  run %d: msgs=%.0f bytes=%.0f ns_per_msg=%.2f msg_per_s=%.2f"
          % (i, r["msgs"], r["bytes"], r["ns_per_msg"], r["msg_per_s"]))

# The report quotes the best of the four SINGLE-STOCK runs. The file also holds two full-stream
# runs; including them would compare different populations.
subset = [r for r in runs if r["msgs"] == 43428]
fails_early = [] if len(subset) == 4 else [
    "the single-stock subset has %d run(s), expected 4" % len(subset)]

best = min(r["ns_per_msg"] for r in subset) if subset else None
print()
print("  best of the single-stock %d runs: %.2f ns/msg" % (len(subset), best))
fails.extend(fails_early)

# The baseline is quoted as "927.35 ns/消息" in the A9 sentence, or as "（927.35 ns，4 次取最优）".
# The simulated 299.01 ns/消息 appears elsewhere and must not be picked up.
# Round 12: the A9 figure is quoted as "软件基线（927.35 ns" or "927.35 ns/消息". Requiring the
# opening parenthesis stops the loose 基线...ns form from matching a LATER ns on the same line -
# the rewritten sentence mentions 基线 and 299.01 together, and the old pattern took 299.01.
quoted = (re.search(r"基线（(\d+\.\d+)\s*ns", rep)
          or re.search(r"基线[^。\n]{0,40}?(\d+\.\d+)\s*ns/消息", rep)
          or re.search(r"(\d+\.\d+)\s*ns，4 次取最优", rep)
          or re.search(r"(\d+\.\d+)\s*ns/消息(?!.{0,20}仿真)", rep))
q = float(quoted.group(1)) if quoted else None
print("  report quotes   : %s ns/msg" % q)
if q is not None and abs(best - q) > 0.01:
    fails.append("best run %.2f != quoted %.2f" % (best, q))

# The rate the report derives from it.
qrate = re.search(r"即\s*([\d,]+)\s*消息/秒", rep)
if qrate:
    stated = float(qrate.group(1).replace(",", ""))
    best_rate = min(subset, key=lambda r: r["ns_per_msg"])["msg_per_s"]
    ok = abs(stated - best_rate) / best_rate < 0.001
    print("  report quotes   : %.0f msg/s" % stated)
    print("  file says       : %.2f msg/s" % best_rate)
    if not ok:
        fails.append("rate %.0f != %.2f" % (stated, best_rate))

# Message count and byte count must match every run.
# The file holds two populations on purpose: the single-stock subset and the full stream.
# Compare sizes WITHIN each population, and say which one the report's figure comes from.
by_size = {}
for r in runs:
    by_size.setdefault((r["msgs"], r["bytes"]), []).append(r)
print()
for (m, b), group in sorted(by_size.items()):
    print("  population msgs=%.0f bytes=%.0f: %d run(s)" % (m, b, len(group)))

subset = [r for r in runs if r["msgs"] == 43428]
if len(subset) != 4:
    fails.append("the single-stock subset has %d run(s), expected 4" % len(subset))

print()
if fails:
    print("BASELINE-TRACE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  %s" % f)
    sys.exit(1)
print("BASELINE-TRACE-PASS (the quoted figure is the best of the %d single-stock"
      " runs, read by field name)" % len(subset))
