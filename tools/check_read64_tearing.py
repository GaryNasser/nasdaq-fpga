"""Is every 64-bit register read taken while the counter is stopped?

`read64()` reads LO then HI. If the counter advances between the two reads the value tears. The driver documents this
at one call site and guards it with a plausibility bound - because that site reads while the pipeline may still be
draining.

A guard on a stopped counter is redundant, so this does not demand one everywhere. It demands that each read be
EITHER taken after the pipeline is known idle, OR followed by a check.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
DRV = os.path.join(REPO, "board", "load_overlay.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

lines = io.open(DRV, encoding="utf-8", errors="replace").read().split("\n")

# What establishes that the counters have stopped.
QUIESCENT = re.compile(r"time\.sleep|drain|quiesc|wait.*idle|after the transfer|freebuffer", re.I)
GUARD = re.compile(r"WARN-IMPLAUSIBLE|plausib|tear|re-?read|verify", re.I)

calls = [(n, l) for n, l in enumerate(lines, 1) if "read64(" in l and "def read64" not in l]
print("read64 call sites: %d" % len(calls))
print()
print("%-6s %-11s %s" % ("line", "protected", "by"))
print("-" * 62)

# Reads whose quiescence is established by control flow rather than by a statement the rule can see.
# Each entry was inspected by hand; the reason is recorded so the exemption cannot outlive its truth.
INSPECTED = {
    "bytes_in = read64(": "taken after the DMA chunk loop has finished - the transfer is complete",
    "bytes_out = read64(": "taken after the DMA chunk loop has finished - the transfer is complete",
}

unsafe = []
for n, line in calls:
    exempt = next((why for k, why in INSPECTED.items() if k in line), None)
    if exempt:
        print("%-6d %-11s %s" % (n, "yes", exempt))
        continue
    # Walk BACK for quiescence evidence, accepting only what is at this read's own indent level or
    # shallower. A sleep inside a loop body protects that body, not a statement after it.
    REARM = re.compile(r"dma\.\w+\.(transfer|sendchannel|recvchannel)|download=True|start\(|submit\(")
    indent = len(lines[n - 1]) - len(lines[n - 1].lstrip())
    quiescent = None
    for k in range(n - 2, max(0, n - 60) - 1, -1):
        prev = lines[k]
        if not prev.strip():
            continue
        pindent = len(prev) - len(prev.lstrip())
        if pindent < indent:
            break                      # left the block that contains this read
        if pindent > indent:
            continue                   # a deeper statement is a different phase
        if REARM.search(prev):
            break
        m = re.search(r"time\.sleep\([^)]*\)|freebuffer\(\)", prev)
        if m:
            quiescent = m.group(0)
            break

    after = "\n".join(lines[n - 1:n + 12])
    guarded = GUARD.search(after)

    if guarded:
        how = "a check follows it"
    elif quiescent:
        how = "counters idle (%s)" % quiescent
    else:
        how = "*** nothing ***"
        unsafe.append((n, line.strip()[:66]))

    print("%-6d %-11s %s" % (n, "yes" if (guarded or quiescent) else "NO", how))

print()
if unsafe:
    print("READ64-TEARING-FAIL (%d 64-bit read(s) taken while the counter may still be moving)" % len(unsafe))
    for n, l in unsafe:
        print("  L%-5d %s" % (n, l))
    sys.exit(1)

print("READ64-TEARING-PASS (every 64-bit read is taken with the counters idle, or checked afterwards)")
