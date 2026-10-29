"""Extend the flag audit: every transfer that feeds the PL must follow a reset.

Three transfer sites exist:

    line 255  --pipeline  MM2S into mold64_reasm   <- needs a reset before it
    line 445  --book      MM2S into mold64_reasm   <- needs a reset before it
    line 706  --loopback  MM2S -> S2MM, PL bypassed <- does NOT need one

The loopback path streams from DDR to DDR and never touches the design, so a CTRL
write there would be meaningless. That distinction matters, because the earlier
version of this audit only counted 0x2->0x1 pairs and could not tell "the loopback
correctly has no reset" from "a PL transfer is missing its reset".

This classifies each transfer by whether it is inside a function that talks to the
PL, and requires a preceding CTRL write only for those.
"""
import io
import re
import sys

PATH = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
lines = io.open(PATH, encoding="utf-8").read().split("\n")

fails = []


def enclosing_def(idx):
    """Name of the enclosing function, or "loopback" when in the DMA loopback.

    The loopback path lives inside main() under a "# ---- DMA loopback" banner
    rather than its own function, so the function name alone cannot classify it.

    The banner must be searched ONLY between the def and the call site, and only as
    a comment line. The first version searched for the substring "loopback" anywhere
    in that range, which matched a later banner and misclassified the --pipeline
    transfer at line 255 as loopback - hiding a real PL transfer from the check.
    """
    for j in range(idx, -1, -1):
        m = re.match(r"def (\w+)", lines[j])
        if m:
            for k in range(j + 1, idx):
                if (lines[k].strip().startswith("#")
                        and "loopback" in lines[k].lower()):
                    return "loopback"
            return m.group(1)
    return "?"


print("transfer sites and their reset")
print()

for i, line in enumerate(lines):
    if "sendchannel.transfer" not in line:
        continue
    fn = enclosing_def(i)
    # Find the nearest CTRL write above, within this function.
    ctrl = None
    for j in range(i - 1, max(-1, i - 80), -1):
        if lines[j].startswith("def "):
            break
        m = re.search(r"REG_M64_CTRL,\s*0x([0-9A-Fa-f]+)", lines[j])
        if m:
            ctrl = (j + 1, m.group(1))
            break

    pl_path = "loopback" not in fn.lower()

    # A reset write must appear above the transfer in the same function. 0x2 is reset-only;
    # 0x3 is reset+enable in one word (the --legacy-reset path). Without this condition the
    # check passes a transfer that enables without ever resetting - the defect in its name.
    # A reset that only executes under --legacy-reset does not protect the default path.
    # Scanning upward, a write is conditional if the nearest preceding statement at lower
    # indentation is an `if args.legacy_reset`.
    def is_conditional(idx):
        indent = len(lines[idx]) - len(lines[idx].lstrip())
        for k in range(idx - 1, max(-1, idx - 80), -1):
            ln = lines[k]
            if not ln.strip():
                continue
            ind = len(ln) - len(ln.lstrip())
            if ind < indent:
                return "legacy_reset" in ln
        return False

    reset = None
    for j in range(i - 1, max(-1, i - 80), -1):
        if lines[j].startswith("def "):
            break
        m = re.search(r"REG_M64_CTRL,\s*0x([0-9A-Fa-f]+)", lines[j])
        if m and m.group(1) in ("2", "3") and not is_conditional(j):
            reset = (j + 1, m.group(1))
            break

    if pl_path and ctrl is None:
        fails.append("line %d (%s): PL transfer with no CTRL write above it" % (i + 1, fn))
    if pl_path and reset is None:
        fails.append("line %d (%s): PL transfer with no CTRL reset (0x2 or 0x3) above it"
                     % (i + 1, fn))
    if pl_path and ctrl is not None and ctrl[1] not in ("1", "3"):
        fails.append("line %d (%s): nearest CTRL write is 0x%s, unexpected"
                     % (i + 1, fn, ctrl[1]))

    print("  line %-4d %-16s %-22s %s"
          % (i + 1, fn, ("CTRL 0x%s at line %d" % (ctrl[1], ctrl[0]))
             if ctrl else "no CTRL write",
             "PL path" if pl_path else "DDR loopback (PL bypassed)"))

print()
if fails:
    print("FLAG-AUDIT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("FLAG-AUDIT-PASS")
