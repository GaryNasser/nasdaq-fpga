"""Rewrite check_ts_retime to assert the CORRECT invariant, not round 165's broken one.

### What it asserted until round 201

    gt_max_r / lt_min_r computed from delta64_r          TRUE
    (both) consumed inside the completion_r block        TRUE
    delta64_r assigned only under a completion guard     TRUE

All three held, and the design was wrong. **The check verified the shape of the retiming, and the retiming's shape
was the bug**: registering a compare and consuming it on the next cycle pairs it with the wrong value.

### What it must assert now

The property that actually matters is a relationship between the compare and the value it governs - they must be
in the same cycle. Concretely:

    min_delta and max_delta are assigned from delta64_r
    the comparisons on delta64_r that gate those assignments are in the SAME block as the assignments
    i.e. neither `if (lt_min_r)` nor `if (gt_max_r)` appears - the compare is inline

Plus the original guard, which is still true and still worth checking:

    delta64_r <= delta_w happens only under if (completion_valid)

### And keep testing the ARITHMETIC

The shape checks above are necessary but were never sufficient. The bench `tb_repro_pair` carries the invariant
that settles it (`max * count >= sum`); this checker asserts that such a test exists and is registered as a real
pass, so "the shape is right" can never again stand alone.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch", "ts_hist.v")
SIM = os.path.join(REPO, "tools", "run_sims.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(RTL, encoding="latin-1").read()
fails = []


def check(name, cond):
    print("  %-58s: %s" % (name, cond))
    if not cond:
        fails.append(name)


print("RTL structure (%s):" % os.path.basename(RTL))
print()

# Line-based: the nearest enclosing block header above `delta64_r <= delta_w` must be a completion guard.
_guard_ok = False
_lines = src.split("\n")
for _i, _l in enumerate(_lines):
    if re.search(r"delta64_r\s*<=\s*delta_w", _l):
        for _j in range(_i, max(-1, _i - 12), -1):
            _t = _lines[_j].strip()
            if _t.startswith("end") and _j != _i:
                break
            if re.search(r"if \(completion_valid\)", _t):
                _guard_ok = True
                break
        break
check("delta64_r is assigned only under a completion guard", _guard_ok)

check("min_delta is assigned from delta64_r",
      bool(re.search(r"min_delta\s*<=\s*delta64_r", src)))

check("max_delta is assigned from delta64_r",
      bool(re.search(r"max_delta\s*<=\s*delta64_r", src)))

# The round-201 property: the compare is inline, not a registered flag consumed later.
check("no registered lt_min_r flag gates the assignment",
      not re.search(r"if\s*\(\s*lt_min_r\s*\)", src))

check("no registered gt_max_r flag gates the assignment",
      not re.search(r"if\s*\(\s*gt_max_r\s*\)", src))

check("the min compare is inline on delta64_r",
      bool(re.search(r"if \(count_delta == 64'd0 \|\| delta64_r\[31:0\] < min_delta\)", src)))

check("the max compare is inline on delta64_r",
      bool(re.search(r"if \(delta64_r\[31:0\] > max_delta\)", src)))

# Both inline compares must sit in the same always block as the completions.
i_cmp = src.find("if (delta64_r[31:0] > max_delta)")
i_gate = src.find("if (completion_r) begin")
check("the inline compare is inside the same always block as completion_r",
      i_cmp > 0 and i_gate > 0 and abs(i_cmp - i_gate) < 4000)

print()
print("the arithmetic test that backs it up:")
sim = io.open(SIM, encoding="utf-8").read()
check("tb_repro_pair asserts max*count >= sum",
      "mx * cnt) < sm" in io.open(os.path.join(REPO, "tools", "tb_repro_pair.v"),
                                  encoding="utf-8").read())
check("tb_repro_pair is registered as a real pass",
      re.search(r'"ts_pair".*KIND_PASS', sim) is not None)

print()
if fails:
    print("TS-RETIME-INVARIANT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)

print("TS-RETIME-INVARIANT-PASS (compare and use share a cycle; the arithmetic invariant is tested)")
