"""Fail if a golden comparison on the reference capture can end in a silent skip.

`_book_test` has three skip exits. Two are requested by the caller (--no-golden,
--repeat N) and are fine. The third fires whenever the parsed message count is not
43428 - which is also what a truncated file or a lossy reassembler produces. Before
round 19 that returned 0, reporting success having verified nothing.

This checks the current code:

  * the reference capture is identified by size AND a content checksum, not by
    message count alone;
  * a message-count mismatch on that capture returns a FAILURE code, not 0;
  * the caller-requested skips still return 0.

Static inspection of the driver, so it needs no board and no mock.
"""
import io
import re
import sys

PATH = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
src = io.open(PATH, encoding="utf-8").read()

fails = []

# 1. reference identity must be by size + checksum
has_size = "REFERENCE_CAPTURE_SIZE" in src
has_digest = "REFERENCE_HEAD_SHA256_16" in src
helper = "_is_reference_capture" in src
print("reference identity by size + checksum : %s"
      % ("yes" if (has_size and has_digest and helper) else "NO"))
if not (has_size and has_digest and helper):
    fails.append("reference capture is not identified by size+checksum")

# 2. the message-count branch must consult it and return non-zero for the reference
m = re.search(r"if nmsg != 43428:(.{0,700})", src, re.S)
if not m:
    fails.append("the nmsg != 43428 branch was not found")
    print("message-count branch                  : NOT FOUND")
else:
    body = m.group(1)
    uses_ref = "_is_reference_capture" in body
    returns_failure = re.search(r"return [1-9]\d*", body) is not None
    print("branch consults the reference id      : %s" % ("yes" if uses_ref else "NO"))
    print("branch returns a failure for it       : %s"
          % ("yes" if returns_failure else "NO"))
    if not uses_ref:
        fails.append("the message-count skip does not consult the reference id")
    if not returns_failure:
        fails.append("the message-count skip can never fail")

# 3. caller-requested skips must still return 0
for label in ("--no-golden given", "--repeat {args.repeat} accumulates"):
    i = src.find(label)
    if i == -1:
        fails.append("skip path not found: %s" % label)
        continue
    tail = src[i:i + 400]
    ok = re.search(r"return 0", tail) is not None
    print("%-38s : %s" % (label[:38], "returns 0 (correct)" if ok else "NO"))
    if not ok:
        fails.append("caller-requested skip no longer returns 0: %s" % label)

print()
if fails:
    print("GOLDEN-PATHS-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("GOLDEN-PATHS-PASS")
