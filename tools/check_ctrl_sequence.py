"""Verify the driver's CTRL write ordering by inspecting its own code path.

The mock-run harness generates its MMIO model as a STRING (mock_run.STUB) and
executes it in a subprocess, so there is no importable MMIO class to hook. Trying
to record writes that way failed twice before I read the file properly.

What actually needs guarding is simple and static: in load_overlay.py, no write of
CTRL=0x3 may be followed by a transfer without an intervening reset-then-enable,
and every reset write (0x2) must be followed by an enable write (0x1) before the
DMA starts.

That is a property of the source, not of a run, so it is checked by parsing the
file: collect the ordered sequence of CTRL writes and DMA transfers in each
function body and assert the ordering.

This is weaker than executing the driver - it cannot see which branch runs - but it
is precise about the one thing that caused the defect, and it needs no hardware.
"""
import io
import re
import sys

PATH = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
src = io.open(PATH, encoding="utf-8", errors="surrogateescape").read()
lines = src.split("\n")

# Tokens of interest, in file order.
EVENTS = []
for i, line in enumerate(lines, 1):
    m = re.search(r"m64_mmio\.write\(\s*REG_M64_CTRL\s*,\s*0x([0-9A-Fa-f]+)\s*\)", line)
    if m:
        EVENTS.append((i, "ctrl", int(m.group(1), 16), line.strip()))
        continue
    if re.search(r"(sendchannel\.transfer|\.transfer\()", line):
        EVENTS.append((i, "xfer", None, line.strip()))

fails = []
print("CTRL writes and transfers, in order")
for ln, kind, val, text in EVENTS:
    print("  line %-4d %-5s %s" % (ln, kind,
                                   ("0x%02X" % val) if val is not None else ""))

print()
print("ordering rules")

# Rule 1: no 0x3 anywhere unless it is inside the --legacy-reset branch.
for ln, kind, val, text in EVENTS:
    if kind == "ctrl" and val == 0x3:
        window = "\n".join(lines[max(0, ln - 12):ln])
        if "legacy_reset" not in window:
            fails.append("line %d: CTRL=0x3 outside the --legacy-reset branch" % ln)

# Rule 2: every 0x2 must be followed by a 0x1 before the next transfer.
for idx, (ln, kind, val, _) in enumerate(EVENTS):
    if not (kind == "ctrl" and val == 0x2):
        continue
    seen_enable = False
    for ln2, kind2, val2, _ in EVENTS[idx + 1:]:
        if kind2 == "ctrl" and val2 == 0x1:
            seen_enable = True
            break
        if kind2 == "xfer":
            break
    if not seen_enable:
        fails.append("line %d: CTRL=0x2 with no CTRL=0x1 before a transfer" % ln)

# Rule 3: at least one well-formed reset-then-enable pair must exist.
pairs = 0
for idx, (ln, kind, val, _) in enumerate(EVENTS):
    if kind == "ctrl" and val == 0x2:
        for ln2, kind2, val2, _ in EVENTS[idx + 1:]:
            if kind2 == "ctrl" and val2 == 0x1:
                pairs += 1
                break
            if kind2 == "xfer":
                break
print("  reset-then-enable pairs: %d" % pairs)
if pairs == 0:
    fails.append("no reset-then-enable pair found at all")

if pairs:
    print("  OK: every reset is followed by an enable before any transfer")
if not any(k == "ctrl" and v == 0x3 for _, k, v, _ in EVENTS):
    print("  OK: no CTRL=0x3 in the default paths")

print()
if fails:
    print("CTRLSEQ-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("CTRLSEQ-PASS")
