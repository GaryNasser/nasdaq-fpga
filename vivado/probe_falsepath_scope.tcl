# Does the L60 false_path extend beyond the AXI-Lite converter it is documented for?
#
# The probe showed the -through filter matches 442 pins. The comment says it covers
# "this converter instance" and that "the datapath (mold64_reasm / itch_parse /
# order_book / ts_hist and the DMA MM2S memory path) remains fully constrained".
#
# 442 pins is a lot for one FSM. This lists them grouped by module so the claim can be
# checked rather than trusted: if any pin lives under a datapath module, the exemption
# is broader than documented and the datapath is NOT fully constrained.

set HERE [file dirname [file normalize [info script]]]
open_project [file join $HERE workspace nasdaq nasdaq.xpr]
open_run impl_1

set pins [get_pins -quiet -hierarchical -filter \
    {NAME =~ *axi_interconnect_0/s00_couplers/auto_pc/*aw_channel_0/aw_cmd_fsm_0/*}]
puts "TOTAL-PINS: [llength $pins]"

# Group by the module instance that owns each pin.
array set counts {}
foreach p $pins {
    set full [get_property NAME $p]
    # Everything up to the last slash is the owning instance path.
    set idx [string last "/" $full]
    set owner [string range $full 0 [expr {$idx - 1}]]
    if {[info exists counts($owner)]} {
        incr counts($owner)
    } else {
        set counts($owner) 1
    }
}
foreach k [lsort -integer -decreasing -command {apply {{a b} {expr {[string compare $a $b]}}}} [array names counts]] {
    puts "OWNER $counts($k) : $k"
}

# Where does the cone of logic ACTUALLY start? Starting points of the exempt paths are
# the real question: a path from a datapath register into this FSM would be a datapath
# path being exempted.
puts "=== start points feeding the exempt FSM ==="
set paths [get_timing_paths -quiet -through $pins -max_paths 20 -nworst 1 -setup]
puts "EXEMPT-PATH-COUNT-REPORTED: [llength $paths]"
foreach tp $paths {
    puts "   START [get_property STARTPOINT_PIN $tp] SLACK [format %.3f [get_property SLACK $tp]]"
}

puts "FALSEPATH-SCOPE-DONE"
close_project
exit 0
