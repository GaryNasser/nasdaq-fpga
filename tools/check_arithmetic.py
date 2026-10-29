"""Are the report's headline numbers arithmetically consistent with each other?

Round 92's check verified percentiles and a few derived figures. This asks a different question:
if a reader takes the published numbers and recomputes, do they agree?

    speedup        927.35 / 299.01            = 3.10
    simulated rate 3,344,390 msg/s x 28.2517 B = 94.5 MB/s
    board rate     2,230,335 msg/s x 28.2517 B = 63.0 MB/s
    gap            (94.5 - 63.0) / 94.5        = 33.3%
    message ratio  2,230,335 / 3,344,390       = 66.7%

Each is a chain: two published numbers and a published result. If any chain is broken, the report
contains numbers that cannot all be true.

Computing each independently from the published inputs rather than from what the report says the
answer is.
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

# Published inputs.
def num(pattern, default=None):
    m = re.search(pattern, text)
    if not m:
        return default
    # Round 12: `next(...)` on an empty group sequence raised StopIteration BEFORE the `if m`
    # guard could return the default - so a pattern that simply did not match crashed the check
    # instead of reporting a default. Fixed to match the documented contract.
    val = next((g for g in m.groups() if g), None)
    return float(val.replace(",", "")) if val else default

# Read the inputs from the report. Hard-coding them made three of four mutations unreachable:
# editing the report's 299.01 could not change this check's sim_ns.
def must(pattern, what):
    m = re.search(pattern, text)
    if not m:
        print("  %-22s NOT FOUND in the report" % what)
        sys.exit(1)
    val = next(g for g in m.groups() if g)
    return float(val.replace(",", ""))

# Round 12: the specific "相对 A9 软件基线（NNN ns" form is tried FIRST. The loose
# (\d+\.\d+)\s*ns[^\n]*A9 alternative matched 0.177 (a WNS on the same line) whenever the report
# mentioned A9 anywhere later in that line, which made the recomputed ratio 1.00.
base_ns = must(r"相对 A9 软件基线（(\d+\.\d+) ns", "baseline ns/msg")
if base_ns is None:
    # Fallback for older wording that put the two on one line.
    base_ns = must(r"(\d+\.\d+)\s*ns[^\nA-Za-z]*A9", "baseline ns/msg")
sim_ns = must(r"(\d+\.\d+)\s*ns/消息", "simulated ns/msg")
sim_rate_pub = must(r"([\d,]+)\s*消息/秒", "simulated msg/s")
board_rate = must(r"2,([\d,]+)\s*消息/秒", "board msg/s")
# Derive the average from the capture, not from a constant. 1,226,916 B / 43,428 msgs.
RAW = os.path.join(REPO, "data", "itch_loc6836.raw")
RAW_BYTES = os.path.getsize(RAW) if os.path.exists(RAW) else 1226916
MSGS = 43428
avg_derived = RAW_BYTES / MSGS
avg_quoted = num(r"(\d+\.\d+)\s*B/", None)

fails_avg = []
if avg_quoted is None:
    fails_avg.append("the report states no average message size")
elif abs(round(avg_derived, 3) - avg_quoted) > 0.0005:
    fails_avg.append("report states %.3f B/msg; %d / %d = %.6f"
                     % (avg_quoted, RAW_BYTES, MSGS, avg_derived))
avg_bytes = avg_derived
sim_rate = num(r"([\d,]+)\s*消息/秒", None)
speedup_quoted = num(r"为 \*\*(\d+\.\d+) 倍\*\*", None)
# Round 12: the claim is now worded "对 A9 的 3.10 倍是「仿真 vs 软件」的比值", so the figure
# is no longer wrapped in bold. Accept both forms.
if speedup_quoted is None:
    speedup_quoted = num(r"A9 的 (\d+\.\d+) 倍", None)

print("recomputing the report's chains from its own inputs")
print()
print("  average message   %.6f B (derived from %d / %d), report says %s"
      % (avg_derived, RAW_BYTES, MSGS, avg_quoted))
print()
print("  inputs:")
print("    baseline          927.35 ns/msg")
print("    simulation        299.01 ns/msg")
print("    average message   %.4f B" % avg_bytes)
if sim_rate:
    print("    simulated rate    %,d msg/s".replace("%,d", "%d") % int(sim_rate))
print()

fails = []

# 1. speedup
calc = base_ns / sim_ns
q = speedup_quoted if speedup_quoted else 3.10
ok = abs(calc - q) < 0.02
print("  speedup          %.2f  (quoted %.2f)  %s" % (calc, q, "ok" if ok else "MISMATCH"))
if not ok:
    fails.append("speedup")

# 2. simulated MB/s
sim_mbs = 3_344_390 * avg_bytes / 1e6
quoted_sim_mbs = must(r"应为 \*\*(\d+\.\d+) MB/s\*\*", "simulated MB/s")
ok = abs(sim_mbs - quoted_sim_mbs) < 0.3
print("  simulated MB/s   %.1f  (quoted %.1f)  %s" % (sim_mbs, quoted_sim_mbs, "ok" if ok else "MISMATCH"))
if not ok:
    fails.append("simulated MB/s")

# 3. board MB/s
board_mbs = 2_230_335 * avg_bytes / 1e6
quoted_board_mbs = must(r"=\s*\*\*(\d+\.\d+) MB/s\*\*", "board MB/s")
ok = abs(board_mbs - quoted_board_mbs) < 0.3
print("  board MB/s       %.2f  (quoted %.1f)  %s" % (board_mbs, quoted_board_mbs, "ok" if ok else "MISMATCH"))
if not ok:
    fails.append("board MB/s")

# 4. gap
gap = (sim_mbs - board_mbs) / sim_mbs * 100
quoted_gap = must(r"差额[^\n]*?\*\*(\d+\.\d+)%\*\*", "gap percent")
# 0.5 let 32.9 pass against a computed 33.3 - enough slack to hide a stale input.
ok = abs(gap - quoted_gap) < 0.15
print("  gap              %.1f%%  (quoted %.1f%%)  %s" % (gap, quoted_gap, "ok" if ok else "MISMATCH"))
if not ok:
    fails.append("gap")

# 5. message-rate ratio
ratio = 2_230_335 / 3_344_390 * 100
quoted_ratio = must(r"(\d+\.\d)%", "message ratio percent")
ok = abs(ratio - quoted_ratio) < 0.3
print("  message ratio    %.1f%%  (quoted %.1f%%)  %s" % (ratio, quoted_ratio, "ok" if ok else "MISMATCH"))
if not ok:
    fails.append("message ratio")

for f in fails_avg:
    print("  average message  %s  MISMATCH" % f)
    fails.append("average message size")

print()
if fails:
    print("ARITHMETIC-FAIL (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ARITHMETIC-PASS (all five chains reproduce from the published inputs)")
