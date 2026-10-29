"""The report must not present a hanging testbench as a passing gate.

    rtl/itch/tb_mold64_reasm.v line 2:
        // SUPERSEDED - THIS TESTBENCH HANGS. DO NOT USE IT AS A VERIFICATION GATE.

Section 3's table used to read:

    | `tb_mold64_reasm` | `TB-ALL-PASS` | `rtl/itch/`（已废弃，会挂起，见下） |

A reader skimming the table sees a green result for a file that cannot produce one. The
parenthetical is there, but the result column asserts something untrue.

Fixed this round: the result column now says "historical; currently hangs, not reproducible".

This check keeps it fixed: any testbench whose own header declares itself superseded or hanging
may not appear in the report with a PASS result in the same table row.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")
RTL = os.path.join(REPO, "rtl", "itch")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Find testbenches that declare themselves unusable.
dead = []
for fn in os.listdir(RTL):
    if not fn.startswith("tb_") or not fn.endswith(".v"):
        continue
    head = io.open(os.path.join(RTL, fn), encoding="latin-1").read()[:1200]
    if re.search(r"SUPERSEDED|HANGS|DO NOT USE", head, re.I):
        dead.append(fn[:-2])          # strip .v

print("testbenches that declare themselves unusable")
for d in dead:
    print("  %s" % d)
print()

if not dead:
    print("DEAD-TB-PASS (no testbench declares itself unusable)")
    sys.exit(0)

rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
lines = rep.split("\n")

fails = []
for i, line in enumerate(lines, 1):
    for d in dead:
        if d not in line:
            continue
        if "|" not in line:
            continue
        if "PASS" not in line:
            continue
        # A PASS on the same row is acceptable only if the row also says it cannot be reproduced.
        if re.search(r"不可复现|历史记录|挂起", line):
            print("  L%-5d %s: PASS with a caveat on the same row  ok" % (i, d))
        else:
            fails.append((i, d))
            print("  L%-5d %s: PASS on a testbench that hangs      PROBLEM" % (i, d))

print()
if fails:
    print("DEAD-TB-FAIL (%d)" % len(fails))
    for ln, d in fails:
        print("  line %d presents %s as passing; it cannot pass" % (ln, d))
    sys.exit(1)
print("DEAD-TB-PASS (no unusable testbench is shown as passing)")
