"""Close the LIMIT that check_rule_agree declares about itself.

Its own L79-L82 says:

    LIMIT: this guard has not been shown to fail. Two forms a parser might miss - always_ff @( )
    and always @ ( ) with a space - are both matched correctly, so neither makes the counts diverge.
    The guard is a cross-check, not a proven one.

**That is an honest statement and it is testable.** The guard's value is "a NEW form the parser misses would
appear as a disagreement", so the test tries forms at increasing distance from what it parses:

    always @*             matched by \\balways\\s*@ ?
    always @ ( posedge )  the docstring says handled
    always_comb           SystemVerilog, no @ at all
    always_latch          SystemVerilog, no @ at all

If a form is added and both counts stay equal, the guard does not see it - the exact failure mode its docstring
predicts, demonstrated rather than asserted.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_rule_agree.py")
RTL = os.path.join(REPO, "rtl", "itch")
MODULE = os.path.join(RTL, "ts_hist.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=900)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("RULE-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(MODULE, encoding="latin-1").read()
if "endmodule" not in body:
    print("RULE-PROOF-INCONCLUSIVE (no endmodule)")
    sys.exit(0)

FORMS = [
    ("always @*", "\n  always @* begin end\n"),
    ("always @ (space)", "\n  always @ (posedge clk) begin end\n"),
    ("always_comb", "\n  always_comb begin end\n"),
    ("always_latch", "\n  always_latch begin end\n"),
]

results = []
print()
for label, snippet in FORMS:
    bk = tempfile.mktemp(suffix=".v")
    shutil.copyfile(MODULE, bk)
    try:
        mutated = body.replace("endmodule", snippet + "\nendmodule", 1)
        io.open(MODULE, "w", encoding="latin-1", newline="\n").write(mutated)
        rc, out = run()
    finally:
        shutil.copyfile(bk, MODULE)
        os.unlink(bk)

    noticed = rc != 0
    m = re.search(r"ts_hist\.v\s+RTL\s+(\d+)\s+check\s+(\S+)", out)
    detail = ("RTL %s check %s" % (m.group(1), m.group(2))) if m else "no counts printed"
    results.append((label, noticed, detail))
    print("  %-20s %-9s %s" % (label, "CAUGHT" if noticed else "MISSED", detail))

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)

missed = [r for r in results if not r[1]]
print()
if rc2 != 0:
    print("RULE-PROOF-FAIL (restoration dirty)")
    sys.exit(1)
if missed:
    print("RULE-PROOF-PASS - the declared LIMIT is now demonstrated:")
    for label, _, detail in missed:
        print("   %-18s is invisible to the parser (%s)" % (label, detail))
    print("   -> adding this form would not be noticed, the failure mode the docstring predicts")
    sys.exit(0)
print("RULE-PROOF-INCONCLUSIVE - every form tried was caught; the LIMIT statement is too pessimistic")
sys.exit(0)
