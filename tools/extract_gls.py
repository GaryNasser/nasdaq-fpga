"""The netlist keeps the RTL hierarchy. `nasdaq_mold64_reasm_0_0_mold64_reasm` is the module.

    nasdaq_mold64_reasm_0_0                  the block-design wrapper
    nasdaq_mold64_reasm_0_0_mold64_reasm     the synthesised mold64_reasm module  <- this one
    plus 249 vendor primitives

So no subtree extraction is needed. If that module's port list matches the behavioural one, the
existing benches can drive the gate-level version unchanged - which is the whole point: same stimuli,
same assertions, deployed netlist.

This script checks the port list and, if it matches, writes a small top that renames the module so
`tb_trickle` (the bench that reproduces the board's trickle pattern) can be pointed at it.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
NET = os.path.join(REPO, "vivado", "gls", "nasdaq_wrapper_timesim.v")
RTL = os.path.join(REPO, "rtl", "itch", "mold64_reasm.v")
OUT = os.path.join(REPO, "vivado", "gls")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(NET, encoding="latin-1").read()
name = "nasdaq_mold64_reasm_0_0_mold64_reasm"

m = re.search(r"^module\s+%s\s*\((.*?)\);" % re.escape(name), src, re.M | re.S)
if not m:
    print("module %s not found with a parenthesised port list" % name)
    # show how it is declared
    i = src.find("module " + name)
    print("  declaration: %r" % src[i:i + 200])
    sys.exit(1)

ports = [p.strip() for p in re.split(r",(?![^\[]*\])", m.group(1)) if p.strip()]
print("gate-level module %s" % name)
print("  %d ports" % len(ports))

names = []
for p in ports:
    toks = p.split()
    names.append(toks[-1])

rtl = io.open(RTL, encoding="latin-1").read()
rm = re.search(r"^module\s+mold64_reasm\b(.*?);", rtl, re.M | re.S)
rtl_ports = sorted(re.findall(r"\b([a-z_][\w]*)\s*(?:,|$)", rm.group(1), re.M)) if rm else []

print()
print("  gate-level port names (first 6): %s" % ", ".join(names[:6]))
print("  behavioural ports: %d" % len(rtl_ports))

# Does the gate-level list contain the ports the benches drive?
NEEDED = ["aclk", "aresetn", "s_axis_tdata", "s_axis_tkeep", "s_axis_tvalid",
          "s_axis_tready", "s_axis_tlast", "m_axis_tdata", "m_axis_tvalid",
          "m_axis_tready", "s_axi_awaddr", "s_axi_wdata", "s_axi_wvalid",
          "s_axi_awready", "s_axi_wready"]
missing = [p for p in NEEDED if p not in names]
print()
print("  ports the benches need, missing from the gate-level module: %s"
      % (", ".join(missing) or "none"))

if missing:
    print()
    print("  all gate-level port names:")
    for p in names:
        print("    %s" % p)
    sys.exit(0)

# Everything the benches drive is present. Write a rename wrapper.
body_start = m.end()
body_end = src.find("\nendmodule", body_start)
body = src[body_start:body_end]

# Rename the module and append the primitive modules it needs.
wrapped = "// Gate-level mould64_reasm extracted from the deployed netlist.\n"
wrapped += "// Module renamed so the existing benches can drive it unchanged.\n"
wrapped += "`timescale 1ns/1ps\n"
wrapped += "`celldefine\n"
wrapped += "module gls_mold64_reasm (%s);\n" % ", ".join(names)
wrapped += body + "\nendmodule\n`endcelldefine\n"

prims = []
for pm in re.finditer(r"^module\s+(\w+)\s*(\(.*?\))?;(.*?)^endmodule", src, re.M | re.S):
    if pm.group(1) == name:
        continue
    prims.append(pm.group(0))

out_path = os.path.join(OUT, "gls_mold64_reasm.v")
with io.open(out_path, "w", encoding="latin-1", newline="\n") as f:
    f.write(wrapped)
    for p in prims:
        f.write("\n`celldefine\n")
        f.write(p)
        f.write("\n`endcelldefine\n")

print()
print("wrote %s (%.1f MB): the module plus %d primitive definitions"
      % (os.path.basename(out_path), os.path.getsize(out_path) / 1e6, len(prims)))
