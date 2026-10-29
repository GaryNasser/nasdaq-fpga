"""Every derived figure must follow from its inputs, at the precision the inputs allow.

93.6 MB/s was 28.0 x 3,344,390, where 28.0 is 28.2517 rounded. The number is reproducible
and 0.9% low. It survived into four documents because nothing recomputed it.

The general fault: a figure computed from a rounded input, then quoted as if exact. The
report also states 28.252 B/message elsewhere, so one document carried two averages for one
capture - which is how a reader multiplying them gets two answers.

This check recomputes what CAN be recomputed from artifacts on disk and compares against
what the report prints:

    average message size   raw bytes / message count
    pipeline MB/s          average x simulated rate
    simulated ns/msg       1e9 / rate
    speedup                A9 ns/msg / simulated ns/msg
    board/pipeline ratio   board rate / simulated rate  (a message-rate ratio)
    mold64 - raw           850 x 12

Figures that need the board (T1 percentiles, board throughput) are not checked here; they
are checked against the board's own output when it is reachable.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
RAW = os.path.join(REPO, "data", "itch_loc6836.raw")
M64 = os.path.join(REPO, "data", "itch_loc6836.mold64")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(REPORT):
    print("FIGURE-DERIVE-FAIL (no report)")
    sys.exit(1)
if not (os.path.exists(RAW) and os.path.exists(M64)):
    print("FIGURE-DERIVE-FAIL (capture files missing; run section 9.2)")
    sys.exit(1)

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

MSGS = 43428
PKTS = 850
RATE = 3344390          # simulated, from the cycle count
A9_NS = 927.35          # measured baseline

raw_size = os.path.getsize(RAW)
m64_size = os.path.getsize(M64)

print("figures recomputed from the capture and the simulated rate")
print()

fails = []


def require(label, printed, computed, tol):
    ok = abs(printed - computed) <= tol
    print("  %-24s printed %-10s computed %-10.2f %s"
          % (label, printed, computed, "ok" if ok else "MISMATCH"))
    if not ok:
        fails.append("%s: printed %s, computed %.2f" % (label, printed, computed))
    return ok


avg = raw_size / MSGS
require("average message size", 28.252, avg, 0.005)

mbps = avg * RATE / 1e6
require("pipeline MB/s", 94.5, mbps, 0.15)

ns = 1e9 / RATE
require("simulated ns/msg", 299.01, ns, 0.05)

speedup = A9_NS / ns
require("speedup", 3.10, speedup, 0.02)

# The board/pipeline ratio is a MESSAGE-rate ratio: 2,230,335 / 3,344,390.
board_rate = 2230335
ratio = board_rate / RATE * 100
require("board/sim ratio %", 66.7, ratio, 0.1)

# Board data rate and the byte-basis gap. Added in round 77 after writing 63.4 into the
# report in round 76 - a value the check did not test because I never listed it.
board_mbps = board_rate * avg / 1e6
require("board MB/s", 63.0, board_mbps, 0.15)

byte_ratio = board_mbps / mbps * 100
require("byte ratio %", 66.7, byte_ratio, 0.1)

gap = (1 - board_mbps / mbps) * 100
require("gap %", 33.3, gap, 0.15)

overhead = m64_size - raw_size
print("  %-24s %-10d %-10d %s"
      % ("mold64 - raw (bytes)", overhead, PKTS * 12,
         "ok" if overhead == PKTS * 12 else "MISMATCH"))
if overhead != PKTS * 12:
    fails.append("capture overhead is %d, expected %d" % (overhead, PKTS * 12))

# The published figures must actually appear.
print()
for label, value in (("94.5 MB/s", "94.5"), ("66.7", "66.7"), ("28.252", "28.252"),
                     ("299.01", "299.01"), ("3.10", "3.10")):
    # Round 4: a plain `in` accepted 66.77 for 66.7, 28.2521 for 28.252, 1299.01 for 299.01 and
    # 3.100 for 3.10 - four figures the report could have changed without this check noticing.
    # Require the digits to end where the figure ends.
    present = re.search(r"(?<![\d.])" + re.escape(value) + r"(?![\d])", text) is not None
    print("  %-24s in report: %s" % (label, present))
    if not present:
        fails.append("%s does not appear in the report" % label)

# The stale rounded value must not be quoted as a result.
stale = [l for l in text.split("\n") if "93.6 MB/s" in l and "此前" not in l]
print()
print("  lines still quoting 93.6 MB/s as a result: %d" % len(stale))
for l in stale[:3]:
    print("     " + l.strip()[:88])
if stale:
    fails.append("93.6 MB/s is still quoted as a result")


# Every MB/s figure in the report must come from something stated, so a new one cannot be
# introduced without a basis. Values that legitimately differ are listed with their source.
KNOWN_MBPS = {
    "94.5": "pipeline: 28.252 B x 3,344,390 msg/s",
    "63.0": "board: 28.252 B x 2,230,335 msg/s",
    # Round 188: the board's PL-only rate from the SAME archived run, so end-to-end and pipeline
    # can be compared on one instrument. 2,225,411 msg/s x 28.252 B.
    "62.9": "board PL-only: 28.252 B x 2,225,411 msg/s",
    "63":   "board, rounded",
    "125":  "1 Gb/s raw",
    "119":  "1 Gb/s with Ethernet framing",
    "615":  "earlier DMA measurement",
    "190":  "byte input port: 1 B/cycle at 190 MHz",
    # Round 257: the board came back. Two figures from one run, different instruments:
    #   62.7  PL-side, 3,748,207 cycles at 190 MHz  ->  1,237,116 B / 0.019727 s
    #   39.2  MM2S transfer loop, host timer       ->  1,237,116 B / 0.031529 s
    "62.7": "board PL-side: 1,237,116 B / (3,748,207 / 190 MHz) s",
    "39.2": "board DMA path: 1,237,116 B / 0.031529 s transfer loop",
    # Round 3: the PL rate varies run to run. 62.8 is the fast end of the five-run spread
    # (3,741,927 cycles = 0.019694 s); the report gives the range 62.3-62.8.
    "62.8": "board PL-side, fast run: 1,237,116 B / 0.019694 s",
    "62.3": "board PL-side, slow run: 1,237,116 B / 0.019848 s",
    # Round 6: two workloads from the message-mix experiment, same byte budget.
    "10.8": "board PL-side, all-add workload: 3,799,568 B / 0.351543 s",
    "77.5": "board PL-side, all-cancel/delete workload: 3,799,410 B / 0.049023 s",
}
print()
print("  every MB/s figure in the report:")
unknown = []
for m in re.finditer(r"(?<![\d.])([\d.]+)\s*MB/s", text):
    v = m.group(1)
    if v in KNOWN_MBPS:
        continue
    # A line recalling a superseded value is prose about a figure, not a figure.
    line = text[text.rfind("\n", 0, m.start()) + 1:text.find("\n", m.start())]
    if any(k in line for k in ("此前", "原写", "曾", "superseded", "previously")):
        continue
    unknown.append((text[:m.start()].count("\n") + 1, v))
for ln, v in unknown:
    print("     L%-5d %s MB/s  <- no stated basis" % (ln, v))
if not unknown:
    print("     all accounted for")

if unknown:
    fails.append("%d MB/s figure(s) with no stated basis" % len(unknown))

print()
if fails:
    print("FIGURE-DERIVE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("FIGURE-DERIVE-PASS (every derivable figure follows from its inputs)")
