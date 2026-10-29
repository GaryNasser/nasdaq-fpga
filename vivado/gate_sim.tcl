# Gate-level simulation of the routed design.
#
# Simulation passes on the RTL, timing closes, and the bitstream is built - but
# nothing so far proves the SYNTHESISED netlist behaves like the RTL. Vivado can
# differ on inferred latches, RAM initial values and X-propagation, and that is
# exactly the class of divergence that would explain a design passing simulation
# while failing on hardware.
#
# This exports the post-implementation netlist and its timing constraints, then
# the testbench is run against the actual gates with the Xilinx primitive
# library.
#
#   vivado -mode batch -source vivado/gate_sim.tcl
#
# Output: vivado/workspace/glsim/nasdaq_gate.v + nasdaq_gate.sdf

set HERE   [file dirname [file normalize [info script]]]
set REPO   [file dirname $HERE]
set WSPACE [file join $HERE workspace]
set PROJ   [file join $WSPACE nasdaq]
set IMPL   [file join $PROJ nasdaq.runs impl_1]
set OUT    [file join $WSPACE glsim]

file mkdir $OUT

set dcp [file join $IMPL nasdaq_wrapper_routed.dcp]
if { ![file exists $dcp] } {
  error "GLS-FAIL: routed checkpoint missing: $dcp"
}
puts "GLS: opening $dcp"
open_checkpoint $dcp

# Sanity: the design must contain the reassembler.
set n [llength [get_cells -hier -filter {NAME =~ "*mold64_reasm*"}]]
puts "GLS: mold64_reasm cells = $n"
if { $n == 0 } {
  error "GLS-FAIL: no mold64_reasm cells in the routed netlist"
}

# Write the gate-level netlist. No unisim primitives are escaped, which keeps
# the file loadable directly by xelab with the simprims/unisims libraries.
set glv [file join $OUT nasdaq_gate.v]
write_verilog -mode timesim -nolib -sdf_anno true -force $glv
puts "GLS: wrote $glv"

# Write the timing annotation for the same netlist.
set sdf [file join $OUT nasdaq_gate.sdf]
write_sdf -force $sdf
puts "GLS: wrote $sdf"

# Summary so the flow's own log records what was exported.
set sz [file size $glv]
puts "GLS-METRICS: netlist_bytes=$sz cells=$n"
puts "GATE-SIM-EXPORT-DONE"
close_project
