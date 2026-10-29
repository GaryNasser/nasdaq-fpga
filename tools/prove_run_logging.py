"""Prove board_recover now writes its output to docs/measurements/.

The board is offline, so the golden run cannot be reached. But the logging block is reachable: it
runs after the remote call and only depends on `r.stdout`.

Test it in isolation: import the module's logging behaviour by running the same code against a
fabricated result object. If the record contains the full stdout, the intercept is correct and
will fire on a real run.

This does NOT prove the whole script works - only that the piece added this round does what it
claims, which is what can be tested without hardware.
"""
import hashlib
import io
import os
import re
import sys
import datetime

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Extract the logging block from board_recover.py and run it against a fake result.
src = io.open(os.path.join(TOOLS, "board_recover.py"), encoding="utf-8").read()
start = src.find("    # Persist the full output.")
end = src.find("    print()\n    if ok:", start)
if start == -1 or end == -1:
    print("BOARD-RUNLOG-PROOF-FAIL (logging block not found)")
    sys.exit(1)

block = src[start:end]
print("logging block: %d characters" % len(block))
print()

# What the block needs in scope.
class Fake:
    stdout = ("BOOK-CNT: add=15334 exe=7\n"
              "TS-STATS: n=19961 p50=40 p95=200 p99=216\n"
              "GOLDEN-OK\n")
    stderr = ""
    returncode = 0

ns = {
    "REPO": REPO,
    "BOARD": "fake-board",
    "cmd": "fake command",
    "r": Fake(),
    "ok": True,
    "io": io,
    "os": os,
}
# Indent-strip the block so it runs at module level.
lines = [l[4:] if l.startswith("    ") else l for l in block.split("\n")]
exec("\n".join(lines), ns)

print()
meas = os.path.join(REPO, "docs", "measurements")
recs = sorted(f for f in os.listdir(meas) if f.startswith("board-recover-"))
if not recs:
    print("BOARD-RUNLOG-PROOF-FAIL (no record written)")
    sys.exit(1)

newest = os.path.join(meas, recs[-1])
body = io.open(newest, encoding="utf-8").read()
print("wrote %s (%d bytes)" % (recs[-1], len(body)))
print()

checks = [
    ("full stdout present", "TS-STATS: n=19961" in body),
    ("BOOK line present", "BOOK-CNT: add=15334" in body),
    ("command recorded", "fake command" in body),
    ("exit code recorded", "remote exit: 0" in body),
    ("verdict recorded", "verdict: OK" in body),
    ("bitstream md5 recorded", "bitstream md5:" in body),
    ("header comment present", body.startswith("# board_recover run")),
]

fails = []
for label, ok in checks:
    print("  %-26s %s" % (label, "yes" if ok else "NO"))
    if not ok:
        fails.append(label)

# Clean up the test record so it is not mistaken for a real run.
os.remove(newest)
print()
print("removed the test record")

print()
if fails:
    print("BOARD-RUNLOG-PROOF-FAIL (%d)" % len(fails))
    sys.exit(1)
print("BOARD-RUNLOG-PROOF-PASS (the run's full output, command, hash and verdict are written)")
