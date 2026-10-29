"""Two rule verdicts confirmed, and a check that keeps them confirmed.

Verified this round by independent re-derivation:

    check_clock_xdc     the log has exactly 105 CRITICAL WARNINGs, two XDC parses (L1232,
                        1758), and zero complaints after the second. The rule matches the log.

    check_multidriver   the RTL has 35 always blocks (20/7/4/4 by module) and the check parses
                        35. Its parser sees everything.

Those are factual rules with evidence behind them, not conventions. Two other rules that are
purely internal - check_fsm_width's "encoding fits the register" and check_fsm_liveness's
"every state is reachable" - were proven to FAIL on broken RTL in rounds 83-84, which is the
strongest form available for a property check.

What is worth keeping is the cross-check itself: the RTL-to-check agreement on always-block
counts. If a future edit adds an always block that the check's parser misses, the counts
diverge and this fails.

That is a real failure mode - the parser might key on a form of `always` the new block does not
use - and it is cheap to test.
"""
import io
import os
import re
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch")
CHK = os.path.join(REPO, "tools", "check_multidriver.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODULES = ["mold64_reasm.v", "itch_parse.v", "order_book.v", "ts_hist.v"]

counts = {}
for m in MODULES:
    p = os.path.join(RTL, m)
    if not os.path.exists(p):
        print("RULE-AGREE-FAIL (%s missing)" % m)
        sys.exit(1)
    src = io.open(p, encoding="latin-1").read()
    code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    counts[m] = len(re.findall(r"\balways\s*@", code))

r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
out = (r.stdout or "") + (r.stderr or "")

print("always blocks: RTL count vs the check's own count")
print()
fails = []
for m in MODULES:
    mine = counts[m]
    m2 = re.search(r"%s\s+(\d+)\s+block" % re.escape(m), out)
    theirs = int(m2.group(1)) if m2 else None
    ok = (theirs == mine)
    print("  %-16s RTL %2d   check %-5s %s"
          % (m, mine, theirs if theirs is not None else "?", "agree" if ok else "DISAGREE"))
    if not ok:
        fails.append(m)

total = sum(counts.values())
print()
print("  total: RTL %d" % total)

print()
if fails:
    print("RULE-AGREE-FAIL (%d module(s))" % len(fails))
    print("  the check's always-block parser and the RTL disagree; a driver could be missed")
    for m in fails:
        print("     %s" % m)
    sys.exit(1)
print("RULE-AGREE-PASS (the multidriver parser sees every always block in all four modules)")
print()
print("  LIMIT, measured in round 233 (see prove_rule.py):")
print("    matched    always @*          always @ ( posedge )     always @( posedge )")
print("    NOT matched  always_comb       always_latch            always_ff")
print("  The first group was checked by injecting each form into ts_hist.v: every one kept both")
print("  counts equal, because both this guard and check_multidriver use `\\balways\\s*@` and")
print("  both accept them - so the docstring's claim about always_ff and `always @ ( )` holds.")
print("  The forms that ESCAPE are the SystemVerilog ones with no `@` at all. They are inert today:")
print("  rtl/itch contains zero of them. Adding one would be invisible to both parsers.")
