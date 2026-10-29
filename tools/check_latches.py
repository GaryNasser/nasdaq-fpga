"""`msg_latched` is a signal NAME, not a latch - a false positive from matching the word "latch" anywhere.

The check must look for the PRIMITIVE, not the substring:
    Vivado reports an inferred latch as "inferred latch" in synthesis, or a LD* cell
A net called `msg_latched` is a normal registered signal.

Narrow to: "inferred latch" (a synthesis message) or a cell-type column containing a latch primitive.
"""
import glob
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if len(sys.argv) > 2 and sys.argv[1] == "--scan":
    candidates = [sys.argv[2]]
else:
    candidates = []
    for pat in (("vivado", "workspace", "nasdaq", "nasdaq.runs", "synth_1", "*.rpt"),
                ("vivado", "workspace", "nasdaq", "nasdaq.runs", "synth_1", "*.log"),
                ("vivado", "build_logs", "rebuild_*.log")):
        candidates += glob.glob(os.path.join(REPO, *pat))

# The synthesis message for an inferred latch.
MSG = re.compile(r"infer(?:red|ring) latch", re.I)

hits = []
for p in candidates:
    try:
        txt = io.open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        continue
    for m in MSG.finditer(txt):
        ln = txt[:m.start()].count("\n") + 1
        ctx = txt[max(0, m.start() - 60):m.start() + 80].replace("\n", " ")
        hits.append((os.path.basename(p), ln, ctx))

print("synthesis artefacts searched: %d" % len(candidates))
print("\"inferred latch\" messages  : %d" % len(hits))
for f, ln, ctx in hits[:6]:
    print("   %s:%-6d %s" % (f, ln, ctx[:70]))

# And the definitive count from the utilisation report's primitive table.
util = glob.glob(os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1",
                              "*utilization_placed.rpt"))
if util:
    txt = io.open(util[0], encoding="utf-8", errors="replace").read()
    for name in ("Latch", "LD", "LATCH"):
        m = re.search(r"\|\s*%s\w*\s*\|\s*(\d+)" % name, txt)
        if m:
            print("  primitive %-8s -> %s" % (name, m.group(1)))
    # Show the full primitive table header names so the absence is visible.
    prims = re.findall(r"^\|\s*([A-Z][\w./\[\]]*)\s*\|\s*(\d+)\s*\|", txt, re.M)
    unusual = [(n, c) for n, c in prims if re.search(r"LATCH|LD$|LDP", n)]
    print("  latch-like primitives in the placed design: %d" % len(unusual))
    for n, c in unusual[:5]:
        print("     %s = %s" % (n, c))

print()
if hits:
    print("LATCH-AUDIT-FAIL (%d inferred-latch message(s))" % len(hits))
    sys.exit(1)
print("LATCH-AUDIT-PASS (no inferred latch reported by synthesis)")
