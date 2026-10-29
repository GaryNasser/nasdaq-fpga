"""Do the simulator and the synthesiser compile the SAME RTL files?

Every simulation in this project compiles `REASM`/`PARSE_BOOK`/`CHAIN` source lists from run_sims.py. Synthesis
compiles whatever the Vivado project lists. **If a file is in one and not the other, the tests exercise a design
that was never built, or a build was never simulated** - and no check covers this.

The comparison must be on resolved absolute paths, because the two lists name files differently.
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

# ---- what simulation compiles ------------------------------------------------
sim_src = io.open(os.path.join(TOOLS, "run_sims.py"), encoding="utf-8", errors="replace").read()

# Every .v the simulator compiles: named source lists AND paths written inline in the SUITES table.
sim_files = set()
for m in re.finditer(r"^(REASM|PARSE_BOOK|CHAIN|SRC\w*|BOOK\w*|TS\w*)\s*=\s*\[(.*?)\]",
                     sim_src, re.M | re.S):
    for f in re.findall(r'"([\w./-]+\.v)"', m.group(2)):
        sim_files.add(os.path.basename(f))

# Inline in the suite table: os.path.join(REPO, "rtl", "x.v") or a bare "tb_x.v".
for f in re.findall(r'os\.path\.join\(\s*REPO\s*(?:,\s*"[\w.-]+"\s*)*,\s*"([\w.-]+\.v)"\s*\)',
                    sim_src):
    sim_files.add(os.path.basename(f))
for f in re.findall(r'"([\w.-]+\.v)"', sim_src):
    sim_files.add(os.path.basename(f))

print("simulation RTL files: %d" % len(sim_files))
for f in sorted(sim_files):
    print("   " + f)

# ---- what synthesis compiles --------------------------------------------------
tcl = os.path.join(REPO, "vivado", "create_project.tcl")
syn_files = set()
if os.path.exists(tcl):
    t = io.open(tcl, encoding="utf-8", errors="replace").read()
    for f in re.findall(r"([\w./-]+\.v)\b", t):
        syn_files.add(os.path.basename(f))
    print()
    print("synthesis RTL files (from create_project.tcl): %d" % len(syn_files))
    for f in sorted(syn_files):
        print("   " + f)

# ---- the difference -----------------------------------------------------------
NONTEST = re.compile(r"^(tb_|test_)")
sim_design = {f for f in sim_files if not NONTEST.match(f)}
syn_design = {f for f in syn_files if not NONTEST.match(f)}

print()
print("=== design files (test benches excluded) ===")
print("  in simulation : %d" % len(sim_design))
print("  in synthesis  : %d" % len(syn_design))

only_sim = sorted(sim_design - syn_design)
only_syn = sorted(syn_design - sim_design)
print()
if only_sim:
    print("  SIMULATED BUT NEVER SYNTHESISED (%d):" % len(only_sim))
    for f in only_sim:
        print("     " + f)
if only_syn:
    print("  SYNTHESISED BUT NEVER SIMULATED (%d):" % len(only_syn))
    for f in only_syn:
        print("     " + f)

print()
if only_sim or only_syn:
    print("RTL-PARITY-FAIL (%d difference(s))" % (len(only_sim) + len(only_syn)))
    sys.exit(1)
print("RTL-PARITY-PASS (simulation and synthesis compile the same %d design files)" % len(sim_design))
