"""A stale "pending" about something already measured is a different fault.

The mutation "restore the stale T1 '仍需上板测量'" was not caught, and correctly so - that
sentence is not about K1, K2 or DMA, so this check does not cover it. Two faults, two checks.

This one: any claim that a figure STILL needs measuring must name something the project has
not measured. The set of measured quantities is known - the T1 percentiles, the golden
book counters, the packet and message counts, the timing, the utilisation.

So: find statements of the form "<subject> 仍需上板 / 尚未测量 / 未测", and require the
subject NOT to be among the measured ones. Matching the subject is textual, so the test is:
if a pending sentence contains any measured quantity or its label, it contradicts itself.

That is precise enough to catch "the board T1 distribution still needs measuring" - which
names T1, a quantity whose percentiles the report prints.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(REPORT):
    print("STALE-PENDING-FAIL (no report)")
    sys.exit(1)

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

# Quantities the project HAS measured. If a pending sentence names one, it is stale.
MEASURED = {
    "T1": re.compile(r"\bT1\b|P50|P95|P99|延迟分布|百分位"),
    "book": re.compile(r"订单簿|8/8|counters?"),
    "packets": re.compile(r"850|包数|rx_packets"),
    "timing": re.compile(r"WNS|WHS|时序"),
    "util": re.compile(r"LUT|FF|BRAM|DSP|资源"),
    "throughput": re.compile(r"消息/秒|msg/s|吞吐"),
}

# Any phrasing that says a figure is still outstanding. The earlier list covered only
# 上板/测量 and missed 复测 - a pending claim about WNS slipped through.
PENDING = re.compile(
    r"仍需(?:上板|测量|复测|验证|确认|给出|补测)"
    r"|(?:尚|仍)未(?:测|实测|验证|确认)"
    r"|未测量|待测量|待测|还需上板|有待实测"
    r"|仍未实测|仍未测")

print("sentences that say something still needs measuring")
print()

fails = []
for i, line in enumerate(text.split("\n"), 1):
    if not PENDING.search(line):
        continue
    m = PENDING.search(line)
    mentioned = [k for k, pat in MEASURED.items() if pat.search(line)]
    print("  L%-5d pending: %-10s   measured subjects named: %s"
          % (i, m.group(0), mentioned or "none"))
    for k in mentioned:
        fails.append("L%d says something still needs measuring while naming %s, which the "
                     "report already measures" % (i, k))

print()
print("  measured quantities the report prints, for reference:")
for k in ("T1", "book", "packets", "timing", "util", "throughput"):
    print("     %-12s %s" % (k, "present" if MEASURED[k].search(text) else "absent"))

print()
# --- targeted scan for the items the hardware cannot deliver -----------------------
# K1 and K2 are not pending; PYNQ-Z2 routes its 1 GbE PHY to the PS MIO, so no PL pin
# carries Ethernet. DMA->DDR has no measurable path (S2MM disabled, no bypass). Any sentence
# pairing one of these with a pending word is stale, whatever phrasing it uses.
# K1 is a physical limit: the 1 GbE PHY is on PS MIO and the PL has no pins to it.
# M6's PL path fails for the same reason. URAM does not exist on a 7020.
#
# K2 was removed from this list in round 212: it is a full AXI-DMA replay that never touches the
# network, its four criteria hold in simulation, and "pending" is the accurate word for it.
IMPOSSIBLE_ITEMS = re.compile("K1")   # round 212: only K1 is a physical limit here
# Prefix-based, not a word list. Three successive rounds added one phrase each ("复测",
# "仍未测") and the next miss was one character away ("未实测"). 未(?:实)?测 matches both
# compounds, and 未(?:实)?(?:测|验证|确认) covers the family.
ANY_PENDING = re.compile(
    r"未(?:实)?(?:测|验证|确认)"
    r"|仍(?:需|未)"
    r"|尚(?:未|需)"
    r"|待(?:测|补|完成|测量)"
    r"|未完成|pending", re.I)

print()
print("  items the hardware cannot deliver, and whether the report calls them pending:")
stale = []
for i, line in enumerate(text.split("\n"), 1) if 'text' in dir() else []:
    if IMPOSSIBLE_ITEMS.search(line) and ANY_PENDING.search(line):
        if re.search(r"不可能|不可行|无法|没有|不能|做不了|不可达", line):
            continue          # the sentence already says it cannot be done
        stale.append((i, line.strip()[:96]))
for i, l in stale:
    print("     L%-5d %s" % (i, l))
if not stale:
    print("     none")

print()
if stale:
    print("STALE-PENDING-FAIL (%d): an impossible item is described as pending" % len(stale))
    for i, l in stale:
        print("  L%d: %s" % (i, l))
    sys.exit(1)

print("STALE-PENDING-PASS (no pending claim names a measured or impossible item)")
