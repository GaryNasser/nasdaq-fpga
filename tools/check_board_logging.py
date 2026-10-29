"""Both board-driving scripts must save what they measure.

Rounds 103-104 established that six headline figures have no file behind them: they were console
output. This round gave board_recover.py and chunk_sweep.py a record writer.

The regression to guard against is not subtle - a future edit reformats main() and drops the
wrapper, and the next board run's numbers are prose again. The test: does the script contain a
write to docs/measurements/ on its executed path?

Checked structurally, because the board is offline and neither script can be run to completion.
A structural test is weaker than a behavioural one; that limitation is stated in the output.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Scripts that drive the board and produce numbers.
BOARD_SCRIPTS = [
    "board_recover.py",
    "chunk_sweep.py",
]

print("board-driving scripts and whether they persist their output")
print()

fails = []
for name in BOARD_SCRIPTS:
    p = os.path.join(TOOLS, name)
    if not os.path.exists(p):
        print("  %-22s MISSING" % name)
        fails.append(name)
        continue
    src = io.open(p, encoding="utf-8").read()
    code = re.sub(r'""".*?"""', "", src, flags=re.S)

    writes = 'docs' in code and 'measurements' in code and re.search(
        r"\bio\.open\([^)]*rec|\bopen\([^)]*rec|\with\s+io\.open", code)
    records_stdout = bool(re.search(r"r\.stdout|tee\.lines|_Tee", code))
    has_meta = bool(re.search(r"bitstream md5|bit_md5", code))

    # Presence is not enough: the writer must be reached from the entry point. A definition
    # that nothing calls leaves the script printing to the console only.
    reached = False
    entry = re.search(r'if __name__ == .__main__.:\s*\n((?:\s+.+\n?)+)', src)
    if entry:
        body = entry.group(1)
        for fn in ("_run_and_save", "main"):
            if re.search(r"%s\s*\(" % re.escape(fn), body):
                if fn == "main" and re.search(r"_run_and_save\s*\(", code):
                    # main() called directly, while the wrapper exists: the wrapper is bypassed
                    continue
                reached = True
                break

    ok = bool(writes) and records_stdout and has_meta and reached
    print("  %-22s writes=%s stdout=%s metadata=%s reached=%s  %s"
          % (name, bool(writes), records_stdout, has_meta, reached,
             "ok" if ok else "INCOMPLETE"))
    if not ok:
        fails.append(name)

print()
print("  LIMIT: this is a structural test. The board is offline, so neither script can be")
print("  run to completion; the check verifies the writer is present on the executed path,")
print("  not that a real run produced a file. board_recover's writer was exercised against a")
print("  fabricated result in prove_run_logging.py, which is the closest available.")

print()
if fails:
    print("BOARD-LOGGING-FAIL (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("BOARD-LOGGING-PASS (both board scripts write a timestamped record with the bitstream"
      " hash and the full output)")
