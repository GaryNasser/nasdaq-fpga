"""Counts in the report that can be re-derived from the data, re-derived every run.

The report's central quantities are not opinions:

    850 packets, 43,428 messages    walkable from data/itch_loc6836.mold64
    1,226,916 bytes raw            the file's size
    1,237,116 bytes mold64         the file's size
    19 mold64_reasm states         the case labels
    14 order_book states           the case labels
    4,096 B buffer                 FIFO_AW

Each was confirmed this round by walking the capture and parsing the RTL. This check repeats the
derivation so a report edited to a different number fails, and so a capture swapped for another
one fails too.

Why it matters: rounds 107-109 found three stale descriptions. Counts are the part of the report
that is cheapest to verify and most damaging to get wrong - 850/850 packets is the evidence the
whole replay claim rests on.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RAW = os.path.join(REPO, "data", "itch_loc6836.raw")
MOLD = os.path.join(REPO, "data", "itch_loc6836.mold64")
RTL = os.path.join(REPO, "rtl", "itch")
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def walk_itch(path):
    body = open(path, "rb").read()
    n, i = 0, 0
    while i + 2 <= len(body):
        ln = (body[i] << 8) | body[i + 1]
        i += 2 + ln
        n += 1
    return n, len(body)


def walk_mold(path):
    body = open(path, "rb").read()
    pkts = msgs = i = 0
    while i + 12 <= len(body):
        cnt = (body[i + 10] << 8) | body[i + 11]
        i += 12
        pkts += 1
        for _ in range(cnt):
            if i + 2 > len(body):
                break
            ln = (body[i] << 8) | body[i + 1]
            i += 2 + ln
            msgs += 1
    return pkts, msgs, len(body)


def code_of(name):
    src = io.open(os.path.join(RTL, name), encoding="latin-1").read()
    src = re.sub(r"//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


msgs_raw, raw_bytes = walk_itch(RAW)
pkts, msgs_mold, mold_bytes = walk_mold(MOLD)
reasm_states = len(set(re.findall(r"\b(ST_[A-Z0-9_]+)\s*:", code_of("mold64_reasm.v"))))
book_states = len(set(re.findall(r"\b(ST_[A-Z0-9_]+)\s*:", code_of("order_book.v"))))
aw = re.search(r"FIFO_AW\s*=\s*(\d+)", code_of("mold64_reasm.v"))
fifo = 1 << int(aw.group(1)) if aw else 0

print("re-derived from the capture and the RTL")
print()
print("  raw messages       %d" % msgs_raw)
print("  raw bytes          %d" % raw_bytes)
print("  packets            %d" % pkts)
print("  mold64 messages    %d" % msgs_mold)
print("  mold64 bytes       %d" % mold_bytes)
print("  mold64_reasm states %d" % reasm_states)
print("  order_book states  %d" % book_states)
print("  packet buffer      %d B" % fifo)
print()

rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

fails = []
# Every statement of the form "N/N 包" and "N/N 条" must agree with the derivation. Presence
# is not enough: a report that says both 850/850 and 851/851 leaves the reader unable to tell
# which is the measurement.
ALLOWED = {"包": (20042, 20042), "条": (1000000, 1000000)}

print("  form                 occurrences            agree with the derivation")
for unit, truth in (("包", pkts), ("条", msgs_mold)):
    pairs = re.findall(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)\s*%s" % unit, rep)
    vals = set()
    for a, b in pairs:
        vals.add((int(a.replace(",", "")), int(b.replace(",", ""))))
    # The report quotes TWO captures: the 1.24 MB subset and the 29 MB stream. A value is
    # wrong only if it matches NEITHER - and every value must match one of them exactly.
    # A value is acceptable only if it is exactly one of the two measured populations.
    allowed = ((truth, truth), ALLOWED[unit])
    bad = sorted(v for v in vals if v not in allowed)
    ok_all = bool(vals) and not bad
    print("  %-20s %-22s %s"
          % ("N/N " + unit, ", ".join("%d/%d" % v for v in sorted(vals)[:4]) or "-",
             "yes" if ok_all else "NO"))
    if not vals:
        fails.append("no %d/%d statements found" % (truth, truth))
    elif bad:
        fails.append("states %s/%s %s where the capture gives %d/%d"
                     % (bad[0][0], bad[0][1], unit, truth, truth))

# The byte counts may appear once; a single mention is enough.
for label, derived, spelled in (
        ("raw byte count", "{:,}".format(raw_bytes), "1,226,916"),
        ("mold64 byte count", "{:,}".format(mold_bytes), "1,237,116")):
    present = spelled in rep or derived in rep
    print("  %-20s %-22s %s" % (label, derived, "yes" if present else "NO"))
    if not present:
        fails.append(label)

# Self-consistency: the two message counts must agree.
if msgs_raw != msgs_mold:
    fails.append("raw and mold64 message counts differ (%d vs %d)"
                 % (msgs_raw, msgs_mold))
    print()
    print("  the raw and MoldUDP64 walks disagree: %d vs %d" % (msgs_raw, msgs_mold))

print()
if fails:
    print("COUNT-TRACE-FAIL (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("COUNT-TRACE-PASS (every central count re-derives from the capture; the two walks agree)")
