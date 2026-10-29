"""The FIFO_BYTES lesson is documented but not enforced: nothing stops `check_constexpr` from falling back to
Python evaluation.

### The documented lesson

Its docstring says: "The first version of this script re-implemented Verilog constant-expression semantics in Python
and immediately failed to parse the design's own concatenation form... Reimplementing one language's semantics in
another is exactly how the FIFO_BYTES bug is supposed to be caught - not repeated by the checker."

**A docstring is not a guard.** If a future edit added a Python fallback for when xvlog is unavailable - a natural
thing to want - the checker would start re-deriving the very semantics it exists to verify, and the FIFO_BYTES class
of bug could be reintroduced with a green suite.

### What this check asserts

    check_constexpr invokes xvlog/xsim                  it asks the real simulator
    check_constexpr contains no constant arithmetic     it does not re-implement the semantics
    an unavailable simulator is a SKIP (exit 2)         never a silent Python answer

The second is the important one: no `<<`, `|`, `&` on FIFO_AW-adjacent expressions inside the checker.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
P = os.path.join(REPO, "tools", "check_constexpr.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(P, encoding="utf-8", errors="replace").read()

# Strip the docstring and comments: the lesson itself mentions the operators.
body = re.sub(r'"""[\s\S]*?"""', "", src, count=1)
body_nc = re.sub(r"#[^\n]*", "", body)

fails = []

uses_sim = ("xvlog" in src or "xsim" in src) and "timescale" in src
print("  invokes the real simulator                        : %s" % uses_sim)
if not uses_sim:
    fails.append("does not invoke xvlog/xsim")

# Constant arithmetic on the RTL's bit widths inside the checker = reimplementation.
# Any shift or bitwise operator in the checker's own executable code. It has no legitimate use: the
# whole point is that xsim evaluates the RTL, not this script.
# Remove string literals entirely: regexes and messages live there, and their | and ^ are not bitwise.
_no_strings = re.sub(r'"[^"\n]*"', '""', body_nc)
_no_strings = re.sub(r"'[^'\n]*'", "''", _no_strings)
arith = re.findall(r"<<|>>|\|(?!\|)|\^(?!=)|&(?!&)", _no_strings)
print("  re-implements Verilog arithmetic in Python        : %s" % bool(arith))
if arith:
    fails.append("contains constant arithmetic: %s" % arith[:3])

_lines = src.split("\n")
skip_is_nonzero = False
for _i, _l in enumerate(_lines):
    if "SKIPPED" in _l:
        for _j in range(_i, min(_i + 5, len(_lines))):
            if "sys.exit(2)" in _lines[_j]:
                skip_is_nonzero = True
                break
        break
print("  an unavailable simulator exits 2, not 0           : %s" % skip_is_nonzero)
if not skip_is_nonzero:
    fails.append("the SKIP path does not exit 2")

print()
if fails:
    print("CONSTEXPR-GUARD-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)

print("CONSTEXPR-GUARD-PASS (the checker asks xsim, and cannot silently re-derive Verilog semantics)")
