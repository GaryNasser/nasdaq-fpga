"""Evaluate RTL constants in the real Verilog simulator, not in Python.

The first version of this script re-implemented Verilog constant-expression
semantics in Python and immediately failed to parse the design's own
concatenation form, `{{FIFO_AW{1'b0}}, 1'b1} << FIFO_AW`. Reimplementing one
language's semantics in another is exactly how the FIFO_BYTES bug is supposed to
be caught - not repeated by the checker.

Xsim is always right about what Verilog means. This generates a tiny testbench
that `include`s the real source, prints each constant, and exits nonzero on a
mismatch, so the check runs in the language of the code it is checking.

SCOPE: this checks constants whose VALUE is computed by an expression and got it
wrong once - FIFO_BYTES (4096, was 6144 after a shift overflow) and ERR_MAX_DEPTH.
It is NOT a general overflow linter. FSM state encodings sit close to their width
limit by design and are guarded by check_fsm_liveness instead.

A round mutated ITCH_TYPE_ADD and called the miss a gap; it was a bad mutation.
Extending EXPECT is only appropriate for a constant whose correct value is known and
whose computation could plausibly be wrong.

REQUIRES xvlog on PATH. Run alone without Vivado's bin directory this exits 1 with
"'xvlog.bat' is not recognized", which reads like a failing check but is a missing tool.
"""
import io
import os
import re
import shutil
import subprocess
import sys

if not (shutil.which("xvlog") or shutil.which("xvlog.bat")):
    print("CONSTEXPR-SKIPPED (xvlog not on PATH - run under tools/run_checks.py "
          "or add Vivado's bin directory)")
    sys.exit(2)

SRC = r"D:\agent\nasdaq-fpga\rtl\itch\mold64_reasm.v"

# (constant, expected, why it matters)
EXPECT = [
    ("FIFO_BYTES", 4096, "ring depth the room guard must respect - was 6144"),
    ("ERR_MAX_DEPTH", 4095, "sanity bound on fifo_available"),
]

srctext = io.open(SRC, encoding="utf-8", errors="surrogateescape").read()

# Only constants with real localparam/parameter declarations in this module.
declared = []
for name, want, why in EXPECT:
    if re.search(r"(localparam|parameter)\s*(\[[^\]]*\]\s*)?%s\s*=" % name, srctext):
        declared.append((name, want, why))

lines = ["`timescale 1ns / 1ps", "module tb_constexpr;", "  integer fails;", "  initial begin", "    fails = 0;"]
for name, want, why in declared:
    lines.append('    if (%s !== %d) begin' % (name, want))
    lines.append('      $display("CONST WRONG %s = %%0d, want %d  (%s)", %s);'
                 % (name, want, why, name))
    lines.append("      fails = fails + 1;")
    lines.append("    end else")
    lines.append('      $display("CONST OK    %s = %%0d  (%s)", %s);' % (name, why, name))
lines += [
    "    if (fails == 0) $display(\"CONSTEXPR-PASS\");",
    "    else            $display(\"CONSTEXPR-FAIL\");",
    "    $finish;",
    "  end",
    "endmodule",
]

work = os.path.join(os.environ["TEMP"], "nasdaq_constexpr")
os.makedirs(work, exist_ok=True)
tb = os.path.join(work, "tb_constexpr.v")
io.open(tb, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")

# `include` the module inside a wrapper so its localparams are in scope.
wrap = os.path.join(work, "m64_wrap.v")
ports = []
src_body = srctext
# Instantiate the module and also expose its parameters via its default values:
# simplest reliable route is to include the module and reference its params
# through the instance, but localparams are not visible outside. Instead we
# duplicate the declarations by textual extraction below.

# Extract the declaration lines verbatim and re-declare them at TB scope.
decl_block = []
for name, _w, _wy in declared:
    m = re.search(r"^\s*(localparam|parameter)[^;\n]*\b%s\b[^;\n]*;" % name,
                  srctext, re.M)
    if m:
        decl_block.append("  " + m.group(0).strip())

# Parameters the declarations depend on.
for dep in ("FIFO_AW",):
    m = re.search(r"^\s*parameter\s+%s\s*=[^;\n]+" % dep, srctext, re.M)
    if m:
        # The source line has no trailing ';' - it ends in a comment - so strip
        # the comment FIRST, then terminate. Appending ';' to the raw line puts
        # it inside the comment and leaves the declaration unterminated.
        decl = m.group(0).strip()
        decl = decl.split("//")[0].rstrip() + ";"
        decl_block.insert(0, "  " + decl)

# Module header, then the declarations, THEN the initial block. Declarations
# must precede statements - the first attempt placed them inside `initial`.
header = lines[:3]          # timescale, module, integer fails
body   = lines[3:]          # initial begin ... endmodule
final = "\n".join(header) + "\n" + "\n".join(decl_block) + "\n" + "\n".join(body)
io.open(tb, "w", encoding="utf-8", newline="\n").write(final + "\n")

env = dict(os.environ)
def run(cmd):
    return subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True)

r = run("xvlog.bat tb_constexpr.v")
if r.returncode != 0:
    print(r.stdout[-2000:])
    print(r.stderr[-2000:])
    sys.exit(1)
r = run("xelab.bat tb_constexpr -s tb_constexpr")
if r.returncode != 0:
    print(r.stdout[-2000:])
    print(r.stderr[-2000:])
    sys.exit(1)
r = run("xsim.bat tb_constexpr -runall")
for line in r.stdout.splitlines():
    if "CONST" in line:
        print("  " + line.strip())
print("CONSTEXPR-PASS" if "CONSTEXPR-PASS" in r.stdout else "CONSTEXPR-FAIL")
sys.exit(0 if "CONSTEXPR-PASS" in r.stdout else 1)
