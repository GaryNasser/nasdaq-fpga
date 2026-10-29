# Out-of-context synthesis of mold64_reasm, for gate-level simulation.
#
# Why: simulation passes on the RTL, timing closes, and the bitstream contains
# the fix - but nothing proves the SYNTHESISED gates behave like the RTL.
# Differences in inferred latches, RAM initial values or X behaviour would only
# appear on real primitives.
#
# The full-design routed netlist cannot be used for this: the Zynq wrapper has
# no top-level ports (the PS is internal), so no testbench can drive it. So the
# reassembler - the module that actually carried the defects - is synthesised
# on its own with the same parameters and simulated against the same real
# capture.
#
# Caveat, stated plainly: out-of-context synthesis does not apply cross-module
# optimisations, so a pass here is strong evidence about the module's mapping
# but not an absolute proof about the shipped bitstream.
set HERE   [file dirname [file normalize [info script]]]
set REPO   [file dirname $HERE]
set WSPACE [file join $HERE workspace]
set OUT    [file join $WSPACE gls_ooc]
file mkdir $OUT

set src [file join $REPO rtl itch mold64_reasm.v]
if { ![file exists $src] } { error "GLS-OOC-FAIL: missing $src" }

read_verilog $src

# Match the instantiation used by the real design and the testbench.
synth_design -top mold64_reasm -part xc7z020clg400-1 \
  -generic SESSION=0x4E41534441513031

set n [llength [get_cells -hier]]
puts "GLS-OOC: total cells = $n"
set ffs [llength [get_cells -hier -filter {IS_SEQUENTIAL}]]
puts "GLS-OOC: sequential cells = $ffs"
if { $ffs < 100 } {
  error "GLS-OOC-FAIL: only $ffs sequential cells - module was pruned"
}

opt_design
write_verilog -mode timesim -nolib -force [file join $OUT mold64_reasm_gate.v]
puts "GLS-OOC: wrote [file join $OUT mold64_reasm_gate.v]"
puts "GLS-OOC-METRICS: cells=$n ffs=$ffs"
puts "GLS-OOC-DONE"
