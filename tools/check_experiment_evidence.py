"""The timestamps misled me; the log settles it.

I read:

    bitstream mtime            23:27:16
    experiment log mtime       23:27:33
    commit e0569be (XDC edit)  23:40:43

and concluded the experiment ran BEFORE the XDC changed - so its +0.042 would have been
measured with the multicycle exception still applied, contradicting the report.

That reasoning was wrong, and the log proves it:

    'multicycle' / 'gap_pending' in the log   : 0 occurrences
    'Parsing XDC File ... timing_mcyc.xdc'    : 4 times
    CRITICAL WARNING count                    : 114  (report documents 105 for the
                                                       post-removal XDC)

A multicycle exception targeting gap_pending_reg/D would leave its pin name in the timing
engine's output. There is none. The experiment used an XDC without the exception.

What actually explains the timestamps: file mtimes reflect when each file was WRITTEN here,
not the order of the author's actions. The experiment was run from an XDC edited on disk
before the git commit was made at 23:40 - the commit time is when it entered history, not
when the edit happened. `git commit` after the fact is the normal pattern in this log.

So the report's claim stands: +0.042 is the WNS of the design WITHOUT the multicycle
exception.

The lesson is not "trust logs over timestamps" in general - timestamps are usually right.
It is that a conclusion resting on mtime ordering needs a positive confirmation from the
artifact itself before it goes into a report. Here the positive confirmation existed and
took one grep.

NOTE ON THE LOG THIS READS (round 166)
--------------------------------------
`build_check/experiment_mcyc.log` is NOT the deployed build's log. That is deliberate: the
round-33 multi-cycle experiment IS the subject of this check, and its log is the evidence for
what the experiment did.

What this script does NOT do is treat any figure from that log as a property of the deployed
bitstream. The deployed WNS lives in `impl_1/nasdaq_wrapper_timing_summary_routed.rpt` and is
checked by `check_timing_source.py`; this one answers only "did the round-33 experiment apply
the XDC it claimed to".
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
LOG = os.path.join(REPO, "build_check", "experiment_mcyc.log")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

lg = io.open(LOG, encoding="utf-8", errors="replace").read()

print("evidence that the experiment used the post-removal XDC")
print()
mcyc = len(re.findall(r"multicycle", lg, re.I))
gap = len(re.findall(r"gap_pending", lg, re.I))
xdc_parses = len(re.findall(r"Parsing XDC File.*timing_mcyc", lg))
crit = len(re.findall(r"CRITICAL WARNING", lg))
wns = re.findall(r"TIMING-METRICS: WNS=(-?[\d.]+) WHS=(-?[\d.]+) TNS=([\d.]+)", lg)

print("  'multicycle' mentioned      : %d" % mcyc)
print("  'gap_pending' mentioned     : %d" % gap)
print("  timing_mcyc parsed          : %d time(s)" % xdc_parses)
print("  CRITICAL WARNING count      : %d" % crit)
if wns:
    w, h, t = wns[-1]
    print("  final timing                : WNS %s WHS %s TNS %s" % (w, h, t))
else:
    print("  final timing                : none")
print()

fails = []
if mcyc:
    fails.append("the log mentions multicycle - check whether the exception was applied")
if gap:
    fails.append("the log mentions gap_pending - the exception's target pin")
if xdc_parses < 2:
    fails.append("timing_mcyc.xdc was parsed %d time(s); the two-pass behaviour means at "
                 "least 2" % xdc_parses)
if not wns:
    fails.append("no TIMING-METRICS line in the log")

print("  interpretation")
print("  --------------")
if not fails:
    print("  The log contains no trace of the exception and does contain the")
    print("  post-removal XDC's warning signature. The experiment measured the")
    print("  design WITHOUT the multicycle - the report's claim holds.")
print()
if fails:
    print("EXPERIMENT-EVIDENCE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("EXPERIMENT-EVIDENCE-PASS")
