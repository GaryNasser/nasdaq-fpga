# Directly report the timing of gap_pending_reg/D in the experiment build.
#
# The routed summary prints only its worst paths, and gap_pending does not appear
# among them. "Not printed" is weak evidence: the path could sit just below the cut.
# report_timing -through gives the path's own slack in one command, which settles
# whether the multicycle exception is unnecessary (slack comfortably positive) or
# hovering near zero (exception still doing real work).
#
# The design is opened from the routed checkpoint so no re-implementation is needed.

set HERE [file dirname [file normalize [info script]]]
set REPO [file dirname $HERE]

open_project [file join $HERE workspace nasdaq nasdaq.xpr]

set impl [get_runs impl_1]
if {[get_property PROGRESS $impl] ne "100%"} {
    puts "IMPL-NOT-COMPLETE: [get_property PROGRESS $impl]"
    exit 1
}

open_run impl_1

puts "=== report_timing through gap_pending_reg/D ==="
set paths [get_timing_paths -through [get_pins -hierarchical -filter \
    {NAME =~ *mold64_reasm_0/inst/gap_pending_reg/D}] -max_paths 1 -nworst 1 -setup]

if {[llength $paths] == 0} {
    puts "GAP-PATH-NOT-FOUND"
} else {
    foreach p $paths {
        set slack [get_property SLACK $p]
        set startpoint [get_property STARTPOINT_PIN $p]
        set endpoint   [get_property ENDPOINT_PIN $p]
        puts "GAP-PATH-SLACK: [format %.4f $slack] ns"
        puts "   start: $startpoint"
        puts "   end  : $endpoint"
        puts "   logic delay: [format %.4f $logic_delay] ns"
    }
}

puts "=== WNS of this build ==="
set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
puts "BUILD-WNS: [format %.4f $wns] ns"

puts "MULTICYCLE-PROBE-DONE"
close_project
exit 0
