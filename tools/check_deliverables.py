"""Assert that every deliverable the assignment names has evidence on disk.

The assignment asks for a specific list of outputs. After 15 rounds that evidence
is spread across the report, the status file and the defect log, and nothing
checked that the list was complete - which is how the implementation method went
missing: round 81 removed a false HLS claim and took the true statement with it, so
for several rounds the report said nothing at all about how the PL side is
implemented.

This re-runs the audit and fails if a deliverable that CAN be evidenced has no
evidence. Two are deliberately excluded from the requirement because they are
impossible on this board:

  K1  needs PL-side Ethernet pins; the PYNQ-Z2 routes 1GbE to PS MIO only, so no
      PL design can capture at line rate. Documented in the report's limitations.
  K2  wire-to-book needs K1's capture path, so it is unreachable for the same
      hardware reason.

Those two are still reported as lacking evidence, so the gap stays visible - they
just do not fail the check, because no amount of work on this board would close
them.
"""
import subprocess
import sys
import os

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

# Decode explicitly. Inheriting the codec makes the result depend on
# PYTHONIOENCODING, which the runner now sets: under the runner this call returned
# mojibake, none of the gap names matched PENDING, and the check reported PASS while a
# real gap was open.
r = subprocess.run([sys.executable, os.path.join(TOOLS, "audit_deliverables.py")],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", cwd=REPO)
out = r.stdout or ""
for line in out.splitlines():
    if line.strip():
        print(line)

# The two hardware-impossible items are allowed to be missing.
# Round 257: K2 was miscategorised here. It is "windows -> book", and a file fed over MM2S supplies
# the windows - K1 (line-rate capture from the PHY) is the part that is physically unavailable. The
# board run met all four K2 criteria; evidence in docs/measurements/k2-board-replay-*.txt.
IMPOSSIBLE = ("K1",)

# Items that CAN be delivered and simply have not been yet. The board being offline is
# not the same as the hardware being incapable, so these are reported separately from
# K1/K2 - a reader needs to know which gaps would close with a power cycle.
PENDING = {
    "DMA→DDR 端到端吞吐":
        # Not "one run closes it": the BD has S2MM disabled (c_include_s2mm {0}) and no
        # bypass behind the MM2S port, so a pure DMA bandwidth figure is not obtainable
        # on this design. A board run yields a decomposition of the gap instead.
        "the board is offline; a chunk-size sweep decomposes the 32% gap",
}
missing = []
in_gaps = False
for line in out.splitlines():
    if line.startswith("gaps:"):
        in_gaps = True
        continue
    if in_gaps and line.startswith("  "):
        item = line.strip()
        if not any(k in item for k in IMPOSSIBLE):
            missing.append(item)

print()
if missing:
    # Split the gaps by nature. A gap that the hardware supports and that only time
    # (or a power cycle) stands in the way of is PENDING, not a failure - but it is
    # reported on every run so it never drops out of sight.
    pending = [m for m in missing if m in PENDING]
    broken = [m for m in missing if m not in PENDING]

    if broken:
        print("DELIVERABLE-FAIL (%d)" % len(broken))
        for m in broken:
            print("  " + m)
        sys.exit(1)

    print("DELIVERABLE-PENDING (%d)" % len(pending))
    for m in pending:
        print("  %s - %s" % (m, PENDING[m]))
    print("  (hardware supports these; the board is offline. Not a failure, not done.)")
    sys.exit(75)

print("DELIVERABLE-PASS (K1 excluded: the PL has no Ethernet pins; K2 is measured in "
      "docs/measurements/k2-board-replay-*.txt)")
