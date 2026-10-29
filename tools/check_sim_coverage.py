"""The chain from simulation to bitstream: same files, every link checkable.

    1  run_sims.py compiles rtl/itch/*.v          the same paths the build uses
    2  BUILD-PROVENANCE.json records MD5s of those files
    3  check_provenance_current re-hashes them    and finds them unchanged

So a passing simulation describes the code that produced the bitstream, provided all three hold.
Two of the links are already checked (run_sims uses those paths; provenance matches). What is not
checked is the FIRST one - that run_sims' file list and the provenance's file list are the same
set. If a module were added to the build and not to the simulation, this pass would still look
complete.

Comparing the two lists.
"""
import io
import json
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
SIMS = os.path.join(REPO, "tools", "run_sims.py")
PROV = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1",
                    "BUILD-PROVENANCE.json")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sims_src = io.open(SIMS, encoding="utf-8").read()
prov = json.load(io.open(PROV, encoding="utf-8"))

# Files the simulation compiles.
sim_files = set()
for m in re.finditer(r'^([A-Z_]+)\s*=\s*\[(.*?)\]', sims_src, re.M | re.S):
    for f in re.findall(r'"([\w.]+\.v)"', m.group(2)):
        sim_files.add(f)
# Multi-line list literals too.
for m in re.finditer(r'\[\s*\n(?:[^\]]*\n)*?\s*\]', sims_src):
    for f in re.findall(r'"([\w.]+\.v)"', m.group(0)):
        sim_files.add(f)

# RTL files the build records.
prov_files = set()
srcs = prov.get("sources") or prov.get("inputs") or {}
if isinstance(srcs, dict):
    prov_files = {os.path.basename(k) for k in srcs if k.endswith(".v")}
elif isinstance(srcs, list):
    prov_files = {os.path.basename(x) for x in srcs if str(x).endswith(".v")}

print("RTL files: simulated vs built")
print()
print("  simulated (%d): %s" % (len(sim_files), ", ".join(sorted(sim_files))))
print("  built     (%d): %s" % (len(prov_files), ", ".join(sorted(prov_files))))
print()

only_sim = sorted(sim_files - prov_files)
only_build = sorted(prov_files - sim_files)

print("  simulated but not built: %s" % (", ".join(only_sim) or "none"))
print("  built but not simulated: %s" % (", ".join(only_build) or "none"))
print()

fails = []
if only_build:
    fails.append("%d RTL file(s) are built but never simulated: %s"
                 % (len(only_build), ", ".join(only_build)))
if not prov_files:
    fails.append("the provenance file lists no .v sources - the comparison is vacuous")

# Sanity: the four core modules must be in both.
CORE = {"mold64_reasm.v", "itch_parse.v", "order_book.v", "ts_hist.v"}
missing = sorted(CORE - prov_files)
if missing:
    fails.append("core module(s) absent from the build record: %s" % ", ".join(missing))

print()
if fails:
    print("SIM-COVERAGE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  %s" % f)
    sys.exit(1)
print("SIM-COVERAGE-PASS (every built RTL file is simulated; the four core modules are in both)")
