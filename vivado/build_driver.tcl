# build_driver.tcl — single Vivado batch entry: create project, then build.
# vivado -mode batch -source build_driver.tcl [-tclargs SKIP_SIM]
#
# CRITICAL: create_project and build_overlay MUST run in the SAME Vivado
# session.  The OOC synth runs (nasdaq_ps7_0_0_synth_1, etc.) are created
# by generate_target in create_project.tcl but are only registered in the
# session where generate_target ran.  close_project loses them, so
# build_overlay.tcl's get_runs would return empty and the OOC runs would
# be invisible.  By sourcing both scripts in one session, the OOC runs
# remain registered and can be launched explicitly.

set HERE [file dirname [file normalize [info script]]]

source [file join $HERE create_project.tcl]
# DO NOT close_project — OOC runs must stay registered for build_overlay
source [file join $HERE build_overlay.tcl]
close_project

puts "BUILD-DRIVER-DONE"
exit 0
