"""Check the one part of the 735/775 comparison that is mechanically verifiable.

The report compares two worst-case figures:

    T1 max        735 cycles   (timestamp difference for the slowest event)
    max_busy_run  775 cycles   (longest FSM occupancy run)

They measure different things and share a starting definition, so their agreement is a
consistency check rather than independent verification - the report now says so.

What IS mechanically checkable is the DIRECTION:

    max_busy_run >= T1 max

An FSM can stay occupied across back-to-back events, so an occupancy run may outlast any
single event's latency. If it came out SMALLER, the two would contradict each other and
one of them would be measuring the wrong interval - a real defect signal.

This reads both numbers from the report and asserts the inequality, so a future edit
that flips either figure is caught.
"""
import io
import os
import re
import sys

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(REPORT):
    print("BUSYRUN-FAIL (no report)")
    sys.exit(1)

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

m_t1 = re.search(r"T1\s*`max`\s*\((\d+)\)|max=(\d+)\s*cycles", text)
m_busy = re.search(r"max_busy_run`?\((\d+)\)|max_busy_run=(\d+)", text)

t1 = None
for g in (m_t1.groups() if m_t1 else ()):
    if g:
        t1 = int(g)
        break
busy = None
for g in (m_busy.groups() if m_busy else ()):
    if g:
        busy = int(g)
        break

print("worst-case figures in the report")
print()
print("  T1 max        : %s" % t1)
print("  max_busy_run  : %s" % busy)
print()

if t1 is None or busy is None:
    print("BUSYRUN-FAIL (could not read both figures)")
    sys.exit(1)

ratio = busy / t1
print("  ratio         : %.3f" % ratio)
print("  direction     : %s" % ("busy_run >= T1 (expected)" if busy >= t1
                               else "busy_run < T1 (CONTRADICTION)"))
print()

fails = []
if busy < t1:
    fails.append("max_busy_run (%d) < T1 max (%d) - the two measurements "
                 "contradict each other" % (busy, t1))
# A ratio far from 1 in either direction would mean they are not measuring
# comparable intervals, which would make the comparison meaningless.
if not (1.0 <= ratio <= 2.0):
    fails.append("ratio %.2f outside the expected 1.0-2.0 - the figures no longer "
                 "describe comparable intervals" % ratio)

if fails:
    print("BUSYRUN-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("BUSYRUN-PASS (busy_run exceeds T1 max by a plausible margin)")
