"""Keep the runbook's numbers in step with the code that defines them.

A runbook is only useful while it is accurate. Every value it quotes - the capture size, the
bitstream MD5, the pipeline rate, the exit codes - is defined in a source file and can
change without anyone remembering to update the prose.

This is the same drift problem the report checks address, applied to the one document an
operator follows under time pressure. A stale number there wastes the recovery window.

Checked:
    capture size        1,237,116      tools/board_recover.py
    bitstream MD5       0ADD0828...    vivado/out/nasdaq.bit
    pipeline rate       93.6 MB/s      tools/chunk_sweep.py
    chunk sizes         1,2,4,8        tools/chunk_sweep.py
    exit codes          0/2/3/4/5/6    tools/board_recover.py
    WNS / WHS           routed report    impl_1/nasdaq_wrapper_timing_summary_routed.rpt

The last row used to point at `build_check/experiment_mcyc.log`, a *different* build's log, so
the runbook could state the shipped design's margin correctly and still fail - and, worse, could
state an obsolete margin and pass. The source is now the routed report of the build in
`vivado/out/`, which is the build the runbook is telling someone to deploy.
"""
import hashlib
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
DOC = os.path.join(REPO, "docs", "RUNBOOK.md")
REC = os.path.join(REPO, "tools", "board_recover.py")
SWEEP = os.path.join(REPO, "tools", "chunk_sweep.py")
LOG = os.path.join(REPO, "build_check", "experiment_mcyc.log")
BIT = os.path.join(REPO, "vivado", "out", "nasdaq.bit")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(DOC):
    print("RUNBOOK-FACT-FAIL (docs/RUNBOOK.md missing)")
    sys.exit(1)

doc = io.open(DOC, encoding="utf-8").read()

print("runbook facts vs their sources")
print()
fails = []


def normalise(text):
    """Digits only, separators removed, so 1,237,116 and 1237116 compare equal."""
    return re.sub(r"[,\s]", "", str(text))


def check(label, value, source):
    # Compare numeric content rather than exact typography: the runbook writes 1,237,116
    # where the code has 1237116, and both are correct.
    present = normalise(value) in normalise(doc) or str(value) in doc
    print("  %-22s %-24s in runbook: %s" % (label, str(value)[:24], present))
    if not present:
        fails.append("%s (%s) is not stated in the runbook - source: %s"
                     % (label, value, source))


# capture size
rec = io.open(REC, encoding="utf-8").read()
m = re.search(r"expected\s*=\s*(\d+)", rec)
if m:
    size = int(m.group(1))
    check("capture size", "{:,}".format(size), "board_recover.py")

# bitstream md5
if os.path.exists(BIT):
    h = hashlib.md5()
    with open(BIT, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    # Round 43: the hash must be the one the runbook calls CURRENT. Presence anywhere is too
    # weak - the runbook also names the replaced hash in a historical note, so a wrong current
    # value still satisfied "appears in the document".
    _want = h.hexdigest().upper()
    _line = next((ln for ln in doc.split("\n")
                  if _want in ln and ("当前" in ln or "current" in ln.lower())), None)
    _present = _line is not None
    print("  %-22s %-24s in runbook: %s" % ("bitstream MD5", _want[:24], _present))
    if not _present:
        fails.append("bitstream MD5 (%s) is not stated as the CURRENT build in the runbook - "
                     "source: out/nasdaq.bit" % _want)

# pipeline rate and chunk sizes
sw = io.open(SWEEP, encoding="utf-8").read()
m = re.search(r"^PIPELINE_RATE_MBPS\s*=\s*([\d.]+)", sw, re.M)
if m:
    check("pipeline rate", m.group(1), "chunk_sweep.py")
m = re.search(r'--sizes",\s*default="([^"]+)"', sw)
if m:
    check("chunk sizes", m.group(1), "chunk_sweep.py")

# exit codes
codes = sorted(set(re.findall(r"return (\d)\b", rec)))
for c in codes:
    check("exit code %s" % c, "| %s |" % c, "board_recover.py")

# timing - from the routed report of the build in vivado/out/, not from an older experiment log
TS = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1",
                  "nasdaq_wrapper_timing_summary_routed.rpt")
if os.path.exists(TS):
    lg = io.open(TS, encoding="utf-8", errors="replace").read()
    m = re.search(r"^\s*(-?\d+\.\d+)\s+-?\d+\.\d+\s+\d+\s+\d+\s+(-?\d+\.\d+)", lg, re.M)
    if m:
        check("current WNS", "+%s" % m.group(1),
              "impl_1/nasdaq_wrapper_timing_summary_routed.rpt")
        check("current WHS", "+%s" % m.group(2),
              "impl_1/nasdaq_wrapper_timing_summary_routed.rpt")

# The runbook must carry the shipped-vs-current distinction, since that is the easiest
# thing to get wrong when the numbers start coming in.
distinction = ("4BB3D7D1" in doc) and ("不重现" in doc or "另一份" in doc)
print()
print("  %-22s %s" % ("shipped-vs-current note", distinction))
if not distinction:
    fails.append("the runbook does not distinguish the shipped bitstream from the one "
                 "being deployed")

print()
if fails:
    print("RUNBOOK-FACT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("RUNBOOK-FACT-PASS")
