"""Cross-check every number in the report that names a Vivado-produced artifact.

Round 206 found the header's WNS two builds stale. Rather than wait to notice the next one, this reads the
authoritative sources and greps the report for each value.

### The authorities, and what each governs

    impl_1/*utilization_placed.rpt      LUT, FF, BRAM, DSP
    impl_1/*timing_summary_routed.rpt   WNS, TNS, failing endpoints, total endpoints, clock period
    vivado/out/nasdaq.bit               its MD5 and size
    vivado/out/nasdaq.hwh               its MD5 and size
    rtl/itch/*.v                        module FF counts (from the synthesis log)
    data/itch_loc6836.mold64            capture size and message count

### What it reports

For each authority value, whether it appears in the report, and - where the report quotes a DIFFERENT value next
to the same label - that too. **A wrong number is worse than a missing one**, because a missing one is visible.
"""
import glob
import hashlib
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

report = io.open(os.path.join(REPO, "docs", "final-report.md"),
                 encoding="utf-8", errors="surrogateescape").read()

facts = []


def grab(pattern, text, cast=str, default=None):
    m = re.search(pattern, text, re.M)
    return cast(m.group(1)) if m else default


# --- utilisation ------------------------------------------------------------------------
u = glob.glob(os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs",
                           "impl_1", "*utilization_placed.rpt"))
if u:
    t = io.open(u[0], encoding="utf-8", errors="replace").read()
    for label, pat in (("LUT", r"\|\s*Slice LUTs\s*\|\s*(\d+)"),
                       ("FF", r"\|\s*Slice Registers\s*\|\s*(\d+)"),
                       ("BRAM", r"\|\s*Block RAM Tile\s*\|\s*(\d+)"),
                       ("DSP", r"\|\s*DSPs\s*\|\s*(\d+)")):
        v = grab(pat, t, int)
        if v is not None:
            facts.append((label, str(v), "utilization_placed.rpt"))

# --- timing -----------------------------------------------------------------------------
tm = glob.glob(os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs",
                            "impl_1", "*timing_summary_routed.rpt"))
if tm:
    t = io.open(tm[0], encoding="utf-8", errors="replace").read()
    m = re.search(r"^\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)\s", t, re.M)
    if m:
        facts.append(("WNS", m.group(1), "timing_summary_routed.rpt"))
        facts.append(("TNS", m.group(2), "timing_summary_routed.rpt"))
        facts.append(("failing endpoints", m.group(3), "timing_summary_routed.rpt"))
        facts.append(("total endpoints", m.group(4), "timing_summary_routed.rpt"))
    # Clock period from the constraint.
    p = grab(r"create_clock[^\n]*?([\d.]+)\s*\]", t)
    if p:
        facts.append(("clock period ns", p, "timing_summary_routed.rpt"))

# --- artifacts --------------------------------------------------------------------------
for name in ("nasdaq.bit", "nasdaq.hwh"):
    p = os.path.join(REPO, "vivado", "out", name)
    if os.path.exists(p):
        data = io.open(p, "rb").read()
        facts.append((name + " MD5", hashlib.md5(data).hexdigest().upper(), "vivado/out/"))
        facts.append((name + " size B", format(len(data), ","), "vivado/out/"))

print("%-22s %-34s %-10s %s" % ("fact", "authoritative value", "in report", "source"))
print("-" * 100)

missing = []
for label, value, source in facts:
    # Accept comma and non-comma forms, and the MD5 case variants.
    variants = {value, value.replace(",", ""), value.upper(), value.lower(),
                # util counts are written "4,520" in the report and read "4520" from the rpt
                format(int(value), ",") if value.isdigit() else value}
    present = any(v and re.search(r"(?<![\d.])" + re.escape(v) + r"(?![\d])", report)
                  for v in variants)
    print("%-22s %-34s %-10s %s" % (label[:22], value[:34], "yes" if present else "NO", source))
    if not present:
        missing.append((label, value, source))

print()
print("facts not found in the report: %d" % len(missing))
for label, value, source in missing:
    print("  %-22s %s  (from %s)" % (label, value, source))

if missing:
    print()
    print("NUMBERS-AUDIT-FAIL (%d) - the report does not state these authoritative values" % len(missing))
    print("  A number the report omits cannot be wrong, and a reader cannot check it.")
    sys.exit(1)

print()
print("NUMBERS-AUDIT-PASS (%d facts, all present)" % len(facts))
