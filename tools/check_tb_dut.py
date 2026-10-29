"""Every test bench must instantiate a design module.

Does each test bench actually instantiate the design module it claims to test?

A test bench that compiles, runs, prints PASS and never instantiates the DUT is the purest form of a green that
means nothing. The suite runs 35 benches and all pass - **but passing only proves the bench printed its token.**

For each bench, find the module it tests (from its name or its content) and confirm at least one instantiation
appears in the source.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
RTL = os.path.join(REPO, "rtl")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The design modules that exist.
design = set()
for root, _dirs, files in os.walk(RTL):
    for f in files:
        if f.endswith(".v") and not f.startswith(("tb_", "test_")):
            design.add(f[:-2])

print("design modules in rtl/: %d  %s" % (len(design), sorted(design)))
print()

benches = sorted(f for f in os.listdir(TOOLS) if f.endswith(".v") and f.startswith(("tb_", "test_")))
print("test benches: %d" % len(benches))
print()

# Negative controls are benches with no DUT by design: they test the RUNNER, not a design module.
NEGATIVE_CONTROL = {"tb_trap.v"}

no_dut = []
unknown = []
for b in benches:
    src = io.open(os.path.join(TOOLS, b), encoding="latin-1").read()

    # Which design modules does this bench name as an instantiation?
    found = set()
    for mod in design:
        # A Verilog instantiation: modname [#(...)] instname (...);
        if re.search(r"\b%s\s*(?:#\s*\(|[A-Za-z_]\w*\s*\()" % re.escape(mod), src):
            found.add(mod)

    if found or b in NEGATIVE_CONTROL:
        continue
    # No known design module instantiated: record whether ANY instantiation-shaped construct exists.
    generic = re.findall(r"^\s*([A-Za-z_]\w*)\s*(?:#\s*\([^)]*\)\s*)?[A-Za-z_]\w*\s*\(", src, re.M)
    upper = [g for g in generic if g[0].isupper() and g not in ("reg", "wire", "input", "output")]
    if upper:
        unknown.append((b, sorted(set(upper))[:3]))
    else:
        no_dut.append(b)

print("benches instantiating a known design module: %d" % (len(benches) - len(no_dut) - len(unknown)))
print()

if unknown:
    print("benches whose DUT is not in rtl/ (checked by name): %d" % len(unknown))
    for b, g in unknown:
        print("   %-26s instantiates %s" % (b, g))

if no_dut:
    print()
    print("BENCHES WITH NO INSTANTIATION AT ALL (%d):" % len(no_dut))
    for b in no_dut:
        print("   " + b)

print()
if no_dut:
    print("TB-DUT-FAIL (%d bench(es) drive nothing)" % len(no_dut))
    sys.exit(1)
print("TB-DUT-PASS (every test bench instantiates a design module)")
