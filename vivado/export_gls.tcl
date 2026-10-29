# Export a gate-level netlist from the routed checkpoint.
#
# The netlist goes to vivado/gls/ so a gate-level simulation of the deployed
# design is possible - the one test that distinguishes "the RTL is wrong" from
# "the synthesis of the RTL is wrong". Run after a build:
#   vivado -mode batch -source vivado/export_gls.tcl

set REPO [file normalize [file join [file dirname [file normalize [info script]]] ..]]
set DCP  [file join $REPO vivado workspace nasdaq nasdaq.runs impl_1 nasdaq_wrapper_routed.dcp]
set GLS  [file join $REPO vivado gls]

open_checkpoint $DCP

file mkdir $GLS

write_verilog -mode timesim -sdf_anno true -force \
    [file join $GLS nasdaq_wrapper_timesim.v]

write_sdf -force [file join $GLS nasdaq_wrapper_timesim.sdf]

puts "GLS-EXPORT-DONE"
