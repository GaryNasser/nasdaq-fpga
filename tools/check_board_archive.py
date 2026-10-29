"""Require every board-facing tool either to archive or to say why it does not.

Round 191 found only two tools write transcripts. The fix is not to force-rewrite the two that work - it is to
make the standard visible and to fail when a NEW tool joins without meeting it.

### What counts as board-facing

A script that runs `ssh` or names the board. Those are the ones whose output cannot be re-created without the
hardware, which is exactly why it must be kept.

### The rule

Each must either:

    import board_archive            and call archive(...)
    write to docs/measurements      directly (the two existing tools do this)
    be listed in EXEMPT with a reason

The exemption list is the escape hatch for scripts whose purpose is to CHECK the archive rather than produce it,
and it is reviewed by naming them.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Scripts that talk to the board but do not PRODUCE a measurement to archive.
EXEMPT = {
    "board_archive.py":       "provides the archiver",
    "check_board_logging.py": "verifies that transcripts exist",
    "check_board_claims.py":  "reads the docs, not the board",
    "check_board_verdict.py": "executes a pure function on fabricated logs",
    "check_board_run_location.py": "reads the docs",
    "mock_board_recover.py":  "simulates the board",
    "prove_board_logging.py": "proves the logging checker",
    "prove_board_verdict.py": "proves the verdict checker",
    "check_chunk_data.py":    "deleted in round 190",
    "check_recover_verdict.py": "mocks the board to test board_recover's verdict; no measurement",
    "test_input_probe.py":    "mocks the board to test probe semantics; no measurement",
}

rows = []
for fn in sorted(os.listdir(TOOLS)):
    if not fn.endswith(".py"):
        continue
    path = os.path.join(TOOLS, fn)
    src = io.open(path, encoding="utf-8", errors="replace").read()
    code = re.sub(r'""".*?"""', "", src, flags=re.S)

    if not re.search(r"\bssh\b|pynq-z2|BOARD\s*=", code):
        continue

    archives = ("board_archive" in code) or ("measurements" in code)
    rows.append((fn, archives, fn in EXEMPT))

print("board-facing tools: %d" % len(rows))
print()
fails = []
for fn, archives, exempt in rows:
    if archives:
        state = "archives"
    elif exempt:
        state = "exempt: %s" % EXEMPT[fn]
    else:
        state = "NO ARCHIVE, NOT EXEMPT"
        fails.append(fn)
    print("  %-32s %s" % (fn, state))

print()
if fails:
    print("BOARD-ARCHIVE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  %s talks to the board but records nothing" % f)
    print()
    print("  Add `from board_archive import archive` and call it with the run's output,")
    print("  or add the script to EXEMPT here with the reason it produces no measurement.")
    sys.exit(1)

print("BOARD-ARCHIVE-PASS (every board-facing tool archives or explains why not)")
