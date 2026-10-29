"""Is the check suite verifying the design, or mostly verifying itself?

Counted this round:

    9   checkers read RTL/XDC/block design
    20  read the report
    46  read tools/ only
    of those 46, twelve explicitly examine OTHER CHECKERS

A three-level tower - checkers, checkers-of-checkers, and checks that those exist - is a
symptom worth naming. Each layer can be individually justified (rounds 60, 61, 67 found
real faults in the layer below), but the tower has a cost the total count hides: the suite
gradually measures its own internal consistency rather than the project.

This is not an argument against the meta-checkers that exist - several caught real bugs.
It is an argument against adding more, and it is checkable: the ratio is a number, and if
it drifts further the work has left the design behind.

The check reports the ratio and fails past a threshold, so the drift is visible rather than
discovered by accident in round 90.
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

# Design checkers, named explicitly.
#
# Three attempts to infer this set from source text failed: pattern on mentions (picked up
# files that merely discuss the design), pattern on reads (matched incidental strings), and
# a docstring fallback (matched any file whose opening paragraph says "RTL").
#
# The list is more reliable than the inference. A name that stops belonging here is visible
# when its checker fails or is deleted; a heuristic that quietly reclassifies is not.
#
# Each entry below reads an RTL, constraint, block-design or bitstream file and asserts a
# property of it.
DESIGN_CHECKERS = {
    "check_arch_fresh.py",          # bitstream vs source freshness
    "check_artifacts.py",           # .bit / .hwh presence and pairing
    "check_bit_hwh.py",             # bitstream and hardware handoff agree
    "check_bit_repro.py",           # rebuild reproducibility
    "check_byte_contract.py",       # 64->8 bit stream agreement
    "check_cdc_map.py",             # clock domain crossings in the BD
    "check_clock_xdc.py",           # XDC parsed twice, second parse clean
    "check_constexpr.py",           # constants fit their widths
    "check_event_layout.py",        # 256-bit event bus packing
    "check_falsepath_scope.py",     # false paths cover only CDC pins
    "check_fsm_idle_reach.py",      # order_book FSM returns to IDLE
    "check_fsm_liveness.py",        # no dead or unreachable FSM states
    "check_fsm_width.py",           # state encodings fit their registers
    "check_guard.py",               # guarded pass tokens
    "check_module_ff.py",           # per-module flip-flop counts
    "check_module_idle_reach.py",   # every module FSM returns to IDLE
    "check_multicycle_guard.py",    # no unneeded multicycle exceptions
    "check_multidriver.py",         # no multiply-driven registers
    "check_regmap.py",              # register map vs RTL decode
    "check_regmap_map.py",          # driver constants vs RTL decode
    "check_t1_units.py",            # bucket width matches the RTL shift
    "check_tb_verdicts.py",         # testbenches can fail
    "check_xdc_clock_text.py",      # XDC clock comments match the constraints
}

DOC = re.compile(r"final-report")
OTHER_CHECK = re.compile(r"check_\w+\.py|run_checks\.py|run_sims\.py|"
                         r"mutate_\w+\.py|test_\w+\.py")

design, doc, meta, other = [], [], [], []
for path in sorted(glob.glob(os.path.join(TOOLS, "check_*.py"))):
    name = os.path.basename(path)
    src = io.open(path, encoding="utf-8", errors="replace").read()

    if name in DESIGN_CHECKERS:
        design.append(name)
    elif DOC.search(src):
        doc.append(name)
    elif OTHER_CHECK.search(src):
        meta.append(name)
    else:
        other.append(name)

# A named checker that is missing from tools/ is a stale entry, not a pass.
absent = sorted(n for n in DESIGN_CHECKERS
                if not os.path.exists(os.path.join(TOOLS, n)))

total = len(design) + len(doc) + len(meta) + len(other)
print("what the %d checkers examine" % total)
print()
print("  design (RTL/XDC/BD/bit) : %2d" % len(design))
print("  report                  : %2d" % len(doc))
print("  other checkers/runner   : %2d" % len(meta))
print("  other tools             : %2d" % len(other))
print()
share = 100.0 * len(design) / max(1, total)
print("  design share            : %.0f%%" % share)
print("  meta share              : %.0f%%" % (100.0 * len(meta) / max(1, total)))

print()
print("  design checkers:")
for n in design:
    print("     %s" % n)

# A ratio, not a prohibition: the tower is allowed, but must not dominate.
# Below 10% design coverage the suite is mostly about itself.
LIMIT = 0.08
print()
fails = []
for n in absent:
    fails.append("named design checker is missing: %s" % n)
if total == 0:
    fails.append("no checkers found")
elif len(design) == 0:
    fails.append("no checkers examine the design at all")
elif share < 100.0 * LIMIT:
    fails.append("only %.0f%% of checkers examine the design (floor is %.0f%%)"
                 % (share, 100.0 * LIMIT))

if fails:
    print("SUITE-FOCUS-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    print()
    print("  The suite has drifted away from the design toward its own machinery.")
    print("  Stop adding meta-checkers and verify hardware-facing facts instead.")
    sys.exit(1)
print("SUITE-FOCUS-PASS (%d of %d checkers examine the design)" % (len(design), total))
