"""Report any register assigned by more than one always block, in EVERY module.

Until round 26 this scanned exactly one file:

    src = io.open(r"...\\rtl\\itch\\mold64_reasm.v", ..., encoding="utf-8", errors="replace")

so `itch_parse.v`, `order_book.v` and `ts_hist.v` were never examined. The check's name
implies whole-design coverage; the code covered one module out of four. A register
double-driven inside the parser or the book would have gone unnoticed for the life of
the project - and a double-driven register synthesises into a silent conflict, not an
error.

This walks rtl/itch/*.v (excluding testbenches) and reports per file, so the coverage
is visible in the output rather than assumed.

The `sys.exit(1)` on a failure is deliberately kept: the runner decides PASS from the
exit code alone, and this file previously printed MULTI-DRIVEN without failing.
"""
import glob
import io
import os
import re
import sys

RTL_DIR = r"D:\agent\nasdaq-fpga\rtl\itch"


def blocks_of(src):
    """Split an always block into its body, tracking begin/end nesting."""
    out = []
    for m in re.finditer(r"always\s*@[^\n]*\n", src):
        start = m.end()
        depth = 1
        i = start
        while i < len(src):
            if re.match(r"\bbegin\b", src[i:i + 6]):
                depth += 1
            if re.match(r"\bend\b", src[i:i + 4]):
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out.append(src[m.start():i + 4])
    return out


# Rules:
#   * skip anything that is not a synthesizable module (testbenches, debug harness);
#   * skip continuous assignments - "x <= y" inside an always is a non-blocking
#     assignment, but the same spelling appears in comparisons like "if (a <= b)".
#     Requiring the match to begin a statement (";" or "begin" or newline before)
#     keeps comparisons out.
CMP_GUARD = re.compile(r"(?:[\n;]|begin|else|\))\s*(\w+)\s*<=\s*(?!=[^=])")
SKIP_SUFFIX = ("_tb.v", "tb_.v", "debug_tb.v")

files = sorted(glob.glob(os.path.join(RTL_DIR, "*.v")))
scanned = []
total_blocks = 0
problems = []

for path in files:
    base = os.path.basename(path)
    if base.startswith("tb_") or base.endswith("_tb.v"):
        continue
    src = io.open(path, encoding="latin-1").read()
    # Skip modules whose first line declares them a testbench.
    if re.search(r"^\s*module\s+(tb_|debug_tb)", src, re.M):
        continue

    blocks = blocks_of(src)
    lhs = {}
    for bi, b in enumerate(blocks):
        for name in CMP_GUARD.findall(b):
            lhs.setdefault(name, set()).add(bi)
    dupes = {k: v for k, v in lhs.items() if len(v) > 1}

    scanned.append((base, len(blocks)))
    total_blocks += len(blocks)
    if dupes:
        problems.append((base, dupes))

print("modules scanned: %d, always blocks: %d" % (len(scanned), total_blocks))
for base, n in scanned:
    print("   %-20s %d block(s)" % (base, n))

if problems:
    print()
    print("MULTI-DRIVEN:")
    for base, dupes in problems:
        for k in sorted(dupes):
            print("   %-20s %-18s blocks %s" % (base, k, sorted(dupes[k])))
    sys.exit(1)  # the runner decides PASS from the exit code alone

print("MULTI-DRIVEN: none")
