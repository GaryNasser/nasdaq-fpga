# Probe what the two set_false_path exceptions actually cover.
set HERE [file dirname [file normalize [info script]]]
open_project [file join $HERE workspace nasdaq nasdaq.xpr]
open_run impl_1

puts "=== false_path L60: aw_cmd_fsm_0 pins matched ==="
set pins [get_pins -quiet -hierarchical -filter \
    {NAME =~ *axi_interconnect_0/s00_couplers/auto_pc/*aw_channel_0/aw_cmd_fsm_0/*}]
puts "FALSEPATH-L60-PIN-COUNT: [llength $pins]"
foreach p [lrange $pins 0 7] {
    puts "   $p"
}

puts "=== false_path L73: MAXIGP0WREADY pins matched ==="
set pins73 [get_pins -quiet -hierarchical -filter \
    {NAME =~ *ps7_0/inst/PS7_i/MAXIGP0WREADY}]
puts "FALSEPATH-L73-PIN-COUNT: [llength $pins73]"
foreach p [lrange $pins73 0 7] {
    puts "   $p"
}

# What do these paths cost? Report timing to the PS ready pin, ignoring the exception
# by asking for the path endpoints rather than the exempt relationship. The exception
# removes them from analysis, so the only honest measure is the pin count plus a
# timing report that bypasses the exception.
puts "=== datapath check: are real datapath paths exempted by accident? ==="
set dp [get_timing_paths -max_paths 1 -nworst 1 -setup]
puts "DATAPATH-WNS: [format %.4f [get_property SLACK $dp]] ns"
set dp_end [get_property ENDPOINT_PIN $dp]
puts "DATAPATH-WNS-ENDPOINT: $dp_end"

puts "FALSEPATH-PROBE-DONE"
close_project
exit 0
