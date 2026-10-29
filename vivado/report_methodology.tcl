# Report critical methodology violations on the routed checkpoint.
#
# Run against an existing routed checkpoint:
#   vivado -mode batch -source vivado/report_methodology.tcl
set REPO [file normalize [file join [file dirname [file normalize [info script]]] ..]]
set DCP  [file join $REPO vivado workspace nasdaq nasdaq.runs impl_1 nasdaq_wrapper_routed.dcp]
set OUT  [file join $REPO vivado gls]

open_checkpoint $DCP

file mkdir $OUT
report_methodology -file [file join $OUT methodology.rpt]

puts "METHODOLOGY-REPORT-DONE"
