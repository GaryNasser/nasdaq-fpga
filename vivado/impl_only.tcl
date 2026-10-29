# impl_only.tcl — place & route + bitstream from the EXISTING synth_1 DCP.
#
# Same checks as build_overlay.tcl's impl stage (module-presence guard,
# connectivity guard, timing gate, artifact pair check), but it does not
# re-run synthesis.  Used to iterate on implementation without paying the
# ~17 minute synth cost each time.
#
#   vivado -mode batch -source vivado/impl_only.tcl
#
# Requires: vivado/workspace/nasdaq/nasdaq.xpr with synth_1 complete.

set REPO [file normalize [file join [file dirname [file normalize [info script]]] ..]]
set WS   [file join $REPO vivado workspace]
set OUT  [file join $REPO vivado out]

open_project [file join $WS nasdaq nasdaq.xpr]

set synth_dcp [file join $WS nasdaq nasdaq.runs synth_1 nasdaq_wrapper.dcp]
if { ![file exists $synth_dcp] } {
  error "IMPL-ONLY: no synthesized DCP at $synth_dcp; run a full build first"
}
puts "IMPL-ONLY: reusing $synth_dcp"

# timing_mcyc.xdc is already a project source (added by create_project.tcl);
# re-reading it just warns "[filemgmt 56-128] already in the project".  Force
# a reload so edits to the constraints take effect for this implementation.
set xdc [file join $REPO vivado timing_mcyc.xdc]
if { [llength [get_files -quiet $xdc]] > 0 } {
  set_property -name {USED_IN} -value {synthesis implementation} -objects [get_files $xdc]
  set_property -name {IS_ENABLED} -value 1 -objects [get_files $xdc]
  puts "IMPL-ONLY: timing_mcyc.xdc already in project (used in impl)"
} else {
  add_files -fileset constrs_1 -norecurse $xdc
  puts "IMPL-ONLY: added timing_mcyc.xdc to project"
}

if { [get_runs impl_1 -quiet] eq "" } {
  create_run impl_1 -parent_run synth_1 -flow {Vivado Implementation 2024}
}
set_property strategy Performance_ExtraTimingOpt [get_runs impl_1]
reset_run impl_1
launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1

if { [get_property PROGRESS [get_runs impl_1]] ne "100%" } {
  error "IMPL-ONLY: impl_1 did not complete (progress [get_property PROGRESS [get_runs impl_1]])"
}

open_run impl_1

# ---- connectivity guard (see build_overlay.tcl) --------------------------
foreach {pin} {S00_ARESETN M00_ARESETN S00_ACLK M00_ACLK} {
  set net [get_nets -quiet -of_objects [get_pins -quiet -hier -filter \
    "NAME =~ *axi_mem_intercon/${pin}"]]
  if { $net eq "" } {
    error "CONNECTIVITY-FAIL: axi_mem_intercon/${pin} is not connected"
  }
  puts "CONNECTIVITY: axi_mem_intercon/${pin} -> $net"
}

# ---- module presence guard ----------------------------------------------
foreach {cell tag min_ffs} {
  order_book_0/inst order_book 300
  mold64_reasm_0/inst mold64_reasm 100
  itch_parse_0/inst itch_parse 100
  ts_hist_0/inst ts_hist 100
} {
  set n [llength [get_cells -quiet -hier -filter \
    "IS_SEQUENTIAL && NAME =~ *${cell}/*"]]
  puts "MODULE-FFS: $tag=$n"
  if { $n < $min_ffs } {
    error "MODULE-PRUNED: $tag has only $n sequential cells (< $min_ffs)"
  }
}

set wns [get_property SLACK [get_timing_paths -delay_type max]]
set whs [get_property SLACK [get_timing_paths -delay_type min]]
report_timing_summary -file [file join $REPO vivado timing_summary.rpt] -warn_on_violation
puts "TIMING-METRICS: WNS=$wns WHS=$whs"

if { $wns < 0 } {
  report_timing -delay_type max -max_paths 20 -nworst 5 \
    -file [file join $REPO vivado timing_fail_paths.rpt]
  error "TIMING-FAIL: WNS = $wns (< 0) at 200 MHz design clock"
}

file mkdir $OUT
file copy -force [file join $WS nasdaq nasdaq.runs impl_1 nasdaq_wrapper.bit] \
                 [file join $OUT nasdaq.bit]
file copy -force [file join $WS nasdaq nasdaq.gen sources_1 bd nasdaq hw_handoff nasdaq.hwh] \
                 [file join $OUT nasdaq.hwh]

foreach f [list [file join $OUT nasdaq.bit] [file join $OUT nasdaq.hwh]] {
  if { ![file exists $f] || [file size $f] == 0 } {
    error "BUILD-FAIL: missing or empty artifact: $f"
  }
}
puts "IMPL-ONLY-OK: WNS=$wns WHS=$whs bit+hwh emitted to $OUT"
close_project
exit 0
