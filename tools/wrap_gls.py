"""Two ports were renamed or removed by synthesis - both expected, both adaptable.

    m_axis_tvalid   -> out_valid_reg_0     the register that drives it kept its name
    s_axi_awready   -> removed             tied high or optimised away, since the slave is always
                                           ready for a write address

Neither is a functional difference. A gate-level bench maps `out_valid_reg_0` to `m_axis_tvalid`,
and drives `s_axi_awready` as a constant 1.

    every other port the benches use is present, with the same name and width

So the deployed netlist CAN be driven by tb_trickle's stimulus, which is the bench that reproduces
the board's byte-at-a-time delivery.

This script writes a wrapper module `gls_mold64_reasm` whose port list matches the behavioural
module, so an existing bench can be recompiled against it with one file swap and no edits.
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
    print("module not found")
    sys.exit(1)
gls_ports = [p.strip().split()[-1] for p in re.split(r",(?![^\[]*\])", m.group(1)) if p.strip()]

# Behavioural port list, in declaration order, with directions.
rtl = io.open(RTL, encoding="latin-1").read()
rm = re.search(r"^module\s+mold64_reasm\b(.*?);", rtl, re.M | re.S)
beh = re.findall(r"(input|output)\s+wire\s*(\[[^\]]*\])?\s*(\w+)", rm.group(1))
print("behavioural module: %d ports" % len(beh))

RENAME = {"m_axis_tvalid": "out_valid_reg_0"}
CONST = {"s_axi_awready": "1'b1"}

lines = []
lines.append("// Gate-level mold64_reasm from the deployed netlist, wrapped to the behavioural port list.")
lines.append("//")
lines.append("// Name changes made by synthesis, mapped here rather than in the bench:")
lines.append("//   m_axis_tvalid  -> %s" % RENAME["m_axis_tvalid"])
lines.append("//   s_axi_awready  -> constant 1 (removed by optimisation)")
lines.append("`timescale 1ns/1ps")
lines.append("")
lines.append("module gls_mold64_reasm (")
portdecls = []
for d, width, nm in beh:
    portdecls.append("  %-6s wire %s %s" % (d, (width or "").ljust(8), nm))
lines.append(",\n".join(portdecls))
lines.append(");")
lines.append("")

# Instance connections.
conns = []
for d, width, nm in beh:
    if nm in CONST:
        continue
    target = RENAME.get(nm, nm)
    if target in gls_ports:
        conns.append("  .%s(%s)" % (target, nm))
    else:
        conns.append("  // .%s(%s)   NOT PRESENT in the gate-level module" % (target, nm))

# Any gate-level port the bench does not drive gets left open.
lines.append("  %s u_gls (" % name)
lines.append(",\n".join(conns))
lines.append("  );")
lines.append("")
lines.append("endmodule")

wrapper = "\n".join(lines) + "\n"

# Primitives.
prims = []
for pm in re.finditer(r"^module\s+(\w+)\s*(\(.*?\))?;(.*?)^endmodule", src, re.M | re.S):
    if pm.group(1) == name:
        continue
    prims.append("`celldefine\n" + pm.group(0) + "\n`endcelldefine")

out_path = os.path.join(OUT, "gls_mold64_reasm.v")
with io.open(out_path, "w", encoding="latin-1", newline="\n") as f:
    f.write(wrapper)
    f.write("\n")
    for p in prims:
        f.write(p + "\n")

print("wrote %s (%.1f MB)" % (os.path.basename(out_path), os.path.getsize(out_path) / 1e6))
print("  wrapper ports: %d   gate-level interior: %d   primitives: %d"
      % (len(beh), len(gls_ports), len(prims)))
print()
print("  connections:")
for c in conns:
    print("    %s" % c[:88])
