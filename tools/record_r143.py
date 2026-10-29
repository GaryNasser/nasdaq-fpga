"""The gate-level netlist now exists. That is this round's deliverable.

    vivado/gls/nasdaq_wrapper_timesim.v     4.6 MB, 251 modules
    vivado/gls/nasdaq_wrapper_timesim.sdf  19.6 MB
    vivado/gls/methodology.rpt              the two critical warnings

Exported from `nasdaq_wrapper_routed.dcp`, which was on disk - the same routed checkpoint the
deployed bitstream came from. Read-only: nothing was rebuilt and the bitstream is untouched.

### What the netlist makes possible

Behavioural simulation has been exhausted (round 142): six benches, all clean, against hardware that
loses exactly the first packet with `err` equal to its byte length.

Gate-level simulation of the SAME netlist that produced the bitstream is the one test that separates
"the RTL is wrong" from "the synthesis of the RTL is wrong".

### The methodology warnings, and what they are not

    TIMING-4   clk_wiz_0/clk_in1 defines a primary clock downstream of clk_fpga_0
    TIMING-27  that primary clock is on a hierarchical pin

Both are about the clock wizard's clock modelling, not about any logic. They affect SDF annotation
accuracy for the clock tree, not functional behaviour.

    LUTAR-1 (warning, not critical)  a LUT drives an asynchronous preset/clear inside the Xilinx
    AXI interconnect's own FIFO - vendor IP, not project code

So the "critical violations may cause functional issues in hardware" warning is not, on inspection,
pointing at mold64_reasm.

### The practical obstacle

`mold64_reasm` appears in the netlist as `mold64_reasm_0`, a hierarchical block inside the wrapper
whose ports are flattened into the top level. It cannot be instantiated standalone with the same port
list as the behavioural module.

Options for a gate-level run:

    a  simulate the whole wrapper with the PS7 stub - heavy, and the AXI DMA must be modelled
    b  extract the mold64_reasm_0 subtree from the netlist into its own module
    c  synthesise mold64_reasm alone and simulate that - NOT the deployed netlist, so it would not
       answer the question

(b) is the one that preserves the deployed logic. It is a scripted extraction: take every module
whose name starts with the instance prefix, re-declare the port list from the instantiation, and
leave the rest behind.
"""
import io
import os
import sys

REPO = r"D:\agent\nasdaq-fpga"
LOG = os.path.join(REPO, "docs", "bringup-defects.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ENTRY = """
## Round 143: the deployed design's gate-level netlist is now on disk

    vivado/gls/nasdaq_wrapper_timesim.v     4.6 MB, 251 modules
    vivado/gls/nasdaq_wrapper_timesim.sdf  19.6 MB

Exported with `write_verilog -mode timesim` from `nasdaq_wrapper_routed.dcp`, the routed checkpoint
the deployed bitstream came from. **Read-only: nothing rebuilt, bitstream untouched.**

That closes round 142's blocker. Behavioural simulation is exhausted - six benches, all clean,
against hardware that loses exactly the first packet with `err` equal to its byte length.

### The methodology warnings, inspected rather than quoted

The export printed "Critical violations ... may cause functional issues in hardware", which sounds
like the defect. Reading the report:

    TIMING-4    clk_wiz_0/clk_in1 defines a primary clock downstream of clk_fpga_0
    TIMING-27   that primary clock sits on a hierarchical pin
    LUTAR-1     a LUT drives an async preset inside the Xilinx AXI interconnect's own FIFO

The first two are clock WIZARD modelling, affecting SDF annotation of the clock tree, not logic. The
third is vendor IP, not project code. **None of them points at mold64_reasm.**

### The obstacle for a gate-level run

`mold64_reasm` is instantiated as `mold64_reasm_0` inside the wrapper with its ports flattened into
the top level, so it cannot be dropped into `tb_gls.v` as-is.

Three routes:

    a  simulate the whole wrapper, modelling the AXI DMA and stubbing the PS7   heavy
    b  extract the mold64_reasm_0 subtree into a standalone module             preserves the deployed
                                                                               logic
    c  synthesise mold64_reasm alone and simulate that                         NOT the deployed
                                                                               netlist

(b) is the only one that answers the question. It is a scripted extraction over a 4.6 MB file.
"""

with io.open(LOG, "a", encoding="utf-8", newline="\n") as f:
    f.write(ENTRY)

after = io.open(LOG, encoding="utf-8", errors="surrogateescape").read()
print("recorded: %s" % ("gate-level netlist is now on disk" in after))
