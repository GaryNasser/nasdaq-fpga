"""Enumerate the reassembler's input-space boundaries from its own RTL, then check which benches cover them.

Rounds 195 and 196 each found a missing case by guessing (empty stream, truncated transfer). Guessing is fine but
it does not tell you when you are done. This derives the list instead.

### Where boundaries come from

A design's edge cases are the finite set of ways its INPUTS can be in a degenerate state, plus the ways its own
state can transition at a limit. For this module the inputs are:

    s_axis_tvalid / tready      beat present, no beat, back-pressure
    s_axis_tlast                asserted at a packet end, inside a packet, never, always
    s_axis_tkeep                all 8 lanes, 1..7 lanes, 0 lanes
    the MoldUDP64 fields        count = 0, count = 1, count = max
                                length = 0, length = max, length spanning many beats
    the session field           matches, does not match, matches mid-payload
    the sequence field          contiguous, gapped, repeated, reversed

The pairwise combos that matter are few; the single-field degenerates are about twenty.

### What this prints

Each degenerate value, and whether some bench's source mentions driving it. **Mentioning is not testing** - but
absence of mention is a strong signal the case is untested, and that is what the two lost rounds were.
"""
import glob
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Every registered bench plus the unregistered ones, as one corpus.
benches = {}
for p in glob.glob(os.path.join(TOOLS, "tb_*.v")):
    benches[os.path.basename(p)] = io.open(p, encoding="latin-1", errors="replace").read()

registered = set(re.findall(r'"(\w+)\.v"', io.open(os.path.join(TOOLS, "run_sims.py"),
                                                   encoding="utf-8").read()))

CASES = [
    ("no beats at all",            [r"EMPTY", r"repeat \(500\)"]),
    ("transfer truncated mid-pkt", [r"TRUNC", r"truncat"]),
    ("tkeep = 1 byte",             [r"8'h01\b"]),
    ("tkeep = 7 bytes",            [r"8'h7[fF]"]),
    ("tkeep = 0 lanes",            [r"8'h00\b", r"tkeep\s*=\s*8'h0"]),
    ("count = 0 message",          [r"count\s*=\s*0\b", r"\b0,\s*0,\s*0\b"]),
    ("length = 0",                 [r"mlen\s*=\s*0", r"len\s*=\s*0\b"]),
    ("length spans many beats",    [r"large_pkt", r"LARGE"]),
    ("TLAST inside a packet",      [r"extra_tlast", r"mid-packet"]),
    ("session mismatch",           [r"session_bad", r"SESSION.*bad"]),
    ("session inside payload",     [r"false_sync"]),
    ("sequence gap",               [r"\bgap\b"]),
    ("TLAST on every beat",        [r"tlast\s*=\s*1.*always", r"every beat"]),
    ("enable dropped mid-stream",  [r"enable.*mid", r"disable.*stream"]),
]

print("%-30s %s" % ("boundary", "bench(es) mentioning it"))
print("-" * 84)
missing = []
for label, pats in CASES:
    hits = []
    for name, body in benches.items():
        if any(re.search(p, body, re.I) for p in pats):
            hits.append(name.replace("tb_", "").replace(".v", ""))
    hits = sorted(set(hits))
    mark = "" if hits else "   <-- NOT MENTIONED"
    print("%-30s %s%s" % (label, ", ".join(hits[:4]) or "(none)", mark))
    if not hits:
        missing.append(label)

print()
print("boundaries with no bench mentioning them: %d" % len(missing))
for m in missing:
    print("  " + m)
