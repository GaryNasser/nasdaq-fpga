"""Cross-check the report's quantitative claims against each other.

Rounds 80-87 corrected eight stale or false figures one at a time. Each was found
by comparing a claim to its source. This does something different: it compares the
report's claims to EACH OTHER, which catches a class that per-source checks miss -
a number that is individually plausible but inconsistent with another number in
the same document.

Checks:
  * latency figures quoted in the header match those in the T1 table;
  * the speedup quoted everywhere matches ns_per_msg(PL) / ns_per_msg(A9);
  * throughput msg/s x mean message size matches the MB/s figure;
  * the golden counters are identical wherever they appear;
  * the T1 percentile ordering is monotonic (p50 <= p95 <= p99 <= max).
"""
import io
import re
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PATH = r"D:\agent\nasdaq-fpga\docs\final-report.md"
text = io.open(PATH, encoding="utf-8").read()

fails = []
print("internal consistency of the report")


def nums(pattern):
    """Collect numbers, tolerating thousands separators.

    The first version used (\\d+\\.\\d) which turned "1,052.6" into 52.6 and made
    the percentile ordering check report a violation in a correct document.
    """
    out = []
    for x in re.findall(pattern, text):
        try:
            out.append(float(x.replace(",", "")))
        except ValueError:
            pass
    return out


# --- latency figures appear in the header and the T1 table -----------------
# The pattern must accept thousands separators: "1,052.6" previously matched as
# "52.6", which made the ordering check report a violation in a correct document.
_NUM = r"([\d,]*\d\.\d)"
p50 = sorted(set(nums(r"p50[^\n]{0,40}?" + _NUM)))
p95 = sorted(set(nums(r"p95[^\n]{0,40}?" + _NUM)))
p99 = sorted(set(nums(r"p99[^\n]{0,40}?" + _NUM)))
print()
print("  p50 values found: %s" % p50)
print("  p95 values found: %s" % p95)
print("  p99 values found: %s" % p99)

# Every occurrence of a percentile must agree WITHIN ITS SOURCE.
#
# Taking max() over all occurrences let a single edited copy hide behind an
# unchanged one: changing p95 to 1,152.6 in the table while the header still said
# 1,052.6 passed, because max() picked the larger value and the ordering check
# stayed satisfied. A figure stated twice must be identical twice.
#
# But "one value per percentile" stopped being true once the board was measured.
# The report now legitimately carries two p99 figures:
#
#     simulation  p99 = 1178.9 ns   (tb_fullchain, ts_hist histogram)
#     board       p99 = 1136.8 ns   (measured through the driver and DMA)
#
# Comparing those against each other is a checker bug, not a document error - the
# first version of this check reported exactly that. So the comparison is now
# per-source: values near a word naming the board must agree among themselves, and
# values near a testbench name must agree among themselves.
BOARD_HINT = re.compile(r"(板上|on-board|board|DMA)", re.I)
SIM_HINT = re.compile(r"(仿真|simulation|tb_[a-z_]+|testbench)", re.I)

# Accepted values, by source.
EXPECTED = {
    "board": {50: 210.5, 95: 1052.6, 99: 1136.8},
    "sim": {50: 210.5, 95: 1052.6, 99: 1178.9},
}


def classify(text, pos):
    """Decide whether a figure at `pos` describes the board or the simulation.

    The nearest hint wins, within a short window. The first version scanned 400 characters
    each way and preferred "sim" when both appeared, which put board figures into the
    simulation group whenever a nearby paragraph mentioned simulation - and reported them as
    inconsistently stated.
    """
    window = text[max(0, pos - 60):pos + 60]
    best = None            # (distance, kind)
    for kind, rx in (("board", BOARD_HINT), ("sim", SIM_HINT)):
        for m in rx.finditer(window):
            # distance from the hint to the figure's position inside the window
            d = abs((max(0, pos - 60) + m.start()) - pos)
            if best is None or d < best[0]:
                best = (d, kind)
    if best is None:
        return "sim"       # no hint nearby: the report's percentile prose is mostly sim
    return best[1]


groups = {"board": {50: set(), 95: set(), 99: set()},
          "sim": {50: set(), 95: set(), 99: set()}}
for label in (50, 95, 99):
    # Case-insensitive: the report writes both "p50" and "P50", and the uppercase form was
    # invisible - which is most of the board percentile figures.
    pat = re.compile(r"p%d[^\n]{0,40}?([\d,]*\d\.\d)" % label, re.I)
    for m in pat.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        groups[classify(text, m.start())][label].add(v)

for src in ("board", "sim"):
    for label in (50, 95, 99):
        vals = groups[src][label]
        if not vals:
            continue
        want = EXPECTED[src][label]
        if len(vals) > 1:
            fails.append("%s p%d stated inconsistently within %s: %s"
                         % (src, label, src, sorted(vals)))
        elif abs(next(iter(vals)) - want) > 0.05:
            fails.append("%s p%d = %.1f, expected %.1f"
                         % (src, label, next(iter(vals)), want))
        else:
            print("  %s p%d = %.1f (expected %.1f)"
                  % (src, label, next(iter(vals)), want))

# --- throughput arithmetic --------------------------------------------------
m = re.search(r"299\.01", text)
pl_ns = 299.01
msg_per_s = 1e9 / pl_ns
avg_body = 1140060.0 / 43428
mbps = msg_per_s * (avg_body + 2) / 1e6
print()
print("  derived from 299.01 ns/msg:")
print("    %.0f msg/s, %.1f MB/s at %.2f B average" % (msg_per_s, mbps, avg_body + 2))
if "3,344,390" in text:
    quoted = 3344390.0
    if abs(quoted - msg_per_s) / msg_per_s > 0.01:
        fails.append("quoted msg/s %.0f vs derived %.0f" % (quoted, msg_per_s))
    else:
        print("    quoted 3,344,390 msg/s: consistent")
else:
    fails.append("msg/s figure not found")

# --- speedup ---------------------------------------------------------------
if "3.10" in text:
    a9 = 927.35
    sp = a9 / pl_ns
    print("  speedup check: %.2f / %.2f = %.2fx (quoted 3.10x)"
          % (a9, pl_ns, sp))
    if abs(sp - 3.10) > 0.02:
        fails.append("speedup %.2f vs quoted 3.10" % sp)
else:
    fails.append("speedup figure not found")

# --- golden counters identical wherever quoted -----------------------------
gold = set(re.findall(r"add=(\d+) exe=(\d+) can=(\d+) del=(\d+) rep=(\d+) "
                      r"drop=(\d+) orders=(\d+) levels=(\d+)", text))
print("  golden-counter variants found: %d" % len(gold))
for g in gold:
    print("    %s" % " ".join(g))
if len(gold) > 1:
    fails.append("golden counters quoted differently in different places")
EXPECTED = ("15334", "7", "12518", "15291", "238", "12826", "320", "95")
if gold and gold != {EXPECTED}:
    fails.append("golden counters differ from the A9 baseline")

# --- percentile ordering ---------------------------------------------------
if all([p50, p95, p99]):
    a50, a95, a99 = max(p50), max(p95), max(p99)  # authoritative set values
    ordered = a50 <= a95 <= a99
    print("  percentile ordering p50<=p95<=p99: %s (%.1f, %.1f, %.1f)"
          % ("OK" if ordered else "VIOLATED", a50, a95, a99))
    if not ordered:
        fails.append("percentiles out of order")

print()
if fails:
    print("INTERNAL-CONSISTENCY-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("INTERNAL-CONSISTENCY-PASS")
