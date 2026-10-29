# Which registers START the paths that the L60 false_path exempts?
#
# The filter matches 442 pins, all inside the AXI-Lite converter's aw_cmd_fsm_0 and a
# few nearby LUTs - no datapath module appears among them, so the documented claim
# ("only this converter instance is exempt; the datapath remains fully constrained")
# holds for the DESTINATION side.
#
# The remaining question is the SOURCE side: a datapath register could feed this FSM,
# in which case that datapath path would be exempted even though no datapath pin is in
# the -through list.
#
# get_timing_paths cannot report an exempted path (the exception removes it), so this
# instead enumerates the fan-in of the FSM's data input pins one level deep, and prints
# their owning modules. One level is enough to tell datapath from control plane.

set HERE [file dirname [file normalize [info script]]]
open_project [file join $HERE workspace nasdaq nasdaq.xpr]
open_run impl_1

set pins [get_pins -quiet -hierarchical -filter \
    {NAME =~ *axi_interconnect_0/s00_couplers/auto_pc/*aw_channel_0/aw_cmd_fsm_0/*}]
puts "TOTAL-PINS: [llength $pins]"

# Collect the owner module of every net feeding these pins.
array set mods {}
foreach p $pins {
    set net [get_nets -quiet -of_objects $p]
    foreach n $net {
        set drv [get_pins -quiet -leaf -of_objects [get_cells -quiet -of_objects $n]]
        foreach d $drv {
            set dn [get_property NAME $d]
            if {[regexp {nasdaq_i/([^/]+)/} $dn -> mod]} {
                if {[info exists mods($mod)]} { incr mods($mod) } else { set mods($mod) 1 }
            }
        }
    }
}
puts "=== fan-in modules (one level) ==="
foreach k [array names mods] {
    puts "FANIN-MODULE $mods($k) : $k"
}

puts "FALSEPATH-FANIN-DONE"
close_project
exit 0
