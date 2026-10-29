# Report the worst paths around the round-149 fix.
#
# Run against an existing routed checkpoint:
#   vivado -mode batch -source vivado/report_after_fix.tcl
set REPO [file normalize [file join [file dirname [file normalize [info script]]] ..]]
set DCP  [file join $REPO vivado workspace nasdaq nasdaq.runs impl_1 nasdaq_wrapper_routed.dcp]
set LOG  [file join $REPO vivado build_logs]

open_checkpoint $DCP

file mkdir $LOG
report_timing_summary -max_paths 1 -file [file join $LOG timing_after_fix.rpt]
report_timing -max_paths 8 -nworst 8 -path_type full_clock_expanded \
    -file [file join $LOG paths_after_fix.rpt]

puts "TIMING-REPORT-DONE"
