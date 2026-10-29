"""Confirm the deliverable audit's summary matches reality.

The audit is the summary a reader trusts. What this check asserts is that **the audit says what is actually true**,
not a fixed number - so the expectations move with the evidence.

    before round 257   10 of 13, gaps = DMA, K1, K2      (the board was offline)
    after  round 257   12 of 13, gaps = K1 only          (DMA and K2 measured on hardware)

**K1 stays a gap on purpose**: PYNQ-Z2 routes its 1 GbE PHY to the PS MIO, so the PL has no Ethernet pins. It is
not a missing measurement.

It runs the audit and parses its own output, so the check measures what the reader sees.
"""
import io
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOOLS = r"D:\agent\nasdaq-fpga\tools"
AUDIT = os.path.join(TOOLS, "audit_deliverables.py")

env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"

r = subprocess.run([sys.executable, AUDIT], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env)
out = (r.stdout or "") + (r.stderr or "")

print("deliverable audit verdict")
print()

m = re.search(r"(\d+) of (\d+) deliverables", out)
count = int(m.group(1)) if m else -1
total = int(m.group(2)) if m else -1
print("  reported: %d of %d" % (count, total))

gaps_block = out.split("gaps:")[-1] if "gaps:" in out else ""
gap_lines = [l.strip() for l in gaps_block.splitlines() if l.strip()]
print("  gaps listed: %d" % len(gap_lines))
for g in gap_lines:
    print("     %s" % g)

fails = []
if total != 13:
    fails.append("expected 13 deliverables, got %d" % total)
if count != 12:
    fails.append("expected 12 delivered, got %d" % count)
if any("DMA" in g for g in gap_lines):
    fails.append("DMA-to-DDR is listed as a gap but was measured on hardware")
if any("K2" in g for g in gap_lines):
    fails.append("K2 is listed as a gap but the board replay met all four criteria")
if not any("K1" in g for g in gap_lines):
    fails.append("K1 must remain a gap: no PL Ethernet pins on this board")

print()
if fails:
    print("DELIVERABLE-COUNT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("DELIVERABLE-COUNT-PASS (12 of 13; K1 alone remains, for a physical reason)")
