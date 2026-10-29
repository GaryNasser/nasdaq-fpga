# build_overlay.tcl — synthesize, place & route, emit .bit + .hwh pair.
# Batch mode: vivado -mode batch -source build_overlay.tcl
# Run AFTER create_project.tcl in the SAME Vivado session (build_driver.tcl
# sources both without closing the project in between).
#
# Flow:
#   1. synth_1 — synthesizes top-level BD wrapper.  Synth wrappers
#      (behavioral models) were removed by export_ip_user_files -sync
#      in create_project.tcl, so synth_1 uses black-box stubs for each
#      IP (fast, tiny).
#   2. After synth_1 completes, it may have re-generated synth wrappers.
#      Remove them again so impl_1 reads only the OOC DCPs.
#   3. impl_1 — reads OOC DCPs, place & route, emits bitstream.

set REPO [file normalize [file join [file dirname [file normalize [info script]]] ..]]
set WS   [file join $REPO vivado workspace]
set OUT  [file join $REPO vivado out]

# Project is already open from create_project.tcl (same session).
# Do NOT call open_project again.

# Platform properties (mirror the official PYNQ-Z2 build_bitstream.tcl)
set_property platform.default_output_type "sd_card" [current_project]
set_property platform.design_intent.embedded "true" [current_project]
set_property platform.design_intent.server_managed "false" [current_project]
set_property platform.design_intent.external_host "false" [current_project]
set_property platform.design_intent.datacenter "false" [current_project]

# ---- Step 1: synth_1 (top-level BD wrapper) ---------------------------
# With synth wrappers removed by export_ip_user_files -sync in
# create_project.tcl, synth_1 uses black-box stubs for each IP.
launch_runs synth_1 -jobs 2
wait_on_run synth_1

if { [get_property PROGRESS [get_runs synth_1]] ne "100%" } {
  error "synth_1 did not complete (progress != 100%)"
}
puts "synth_1 complete"

# ---- Step 2: Remove synth wrappers (behavioral models) ------------------
# synth_1 may have re-generated synth wrappers when it launched OOC runs
# as dependencies. Remove them again so impl_1 reads only the OOC DCPs
# and does NOT synthesize the behavioral models as fabric.
export_ip_user_files -of_objects [get_files nasdaq.bd] -sync -no_script -force
update_compile_order -fileset sources_1

# Verify synth wrappers are gone
set remaining [get_files -of_objects [get_filesets sources_1] -filter {NAME =~ *synth* && NAME =~ *.v && NAME =~ *nasdaq_*}]
if {$remaining ne ""} {
  puts "WARNING: synth wrappers still present after export_ip_user_files:"
  foreach f $remaining { puts "  $f" }
} else {
  puts "Synth wrappers removed — impl_1 will use OOC DCPs only"
}

# ---- Step 2b: Re-load timing constraints --------------------------------
# The read_xdc in create_project.tcl may be cleared by export_ip_user_files
# or synth_1.  Re-load timing_mcyc.xdc after synth_1 (when all cells are
# elaborated) so the constraints are applied during impl_1.
read_xdc [file join $REPO vivado timing_mcyc.xdc]
puts "timing_mcyc.xdc re-loaded after synth_1"



# ---- Step 3: impl_1 + bitstream ----------------------------------------
# Performance_ExtraTimingOpt: ExtraTimingOpt placement + aggressive
# phys_opt_design + aggressive routing.  Performance_Explore closed to
# WNS -0.029 ns (one marginal path in mold64_reasm, 77% route delay), so
# the extra timing optimisation pass is needed to close the last 30 ps.
set_property strategy Performance_ExtraTimingOpt [get_runs impl_1]
launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1

if { [get_property PROGRESS [get_runs impl_1]] ne "100%" } {
  error "impl_1 did not complete (progress != 100%)"
}

# Timing report (constitution IV): check BEFORE copying so a timing-failing
# build leaves no deployable artifacts behind (FR-001 / T009 "no residue").
open_run impl_1

# Diagnostic: dump every clock so the build log proves what the constraints
# matched.  (XDC control flow is not supported; if a clock name is wrong the
# set_clock_groups in timing_mcyc.xdc fails loudly here / at read_xdc.)
puts "=== CLOCKS ==="
foreach c [get_clocks -quiet] {
  puts "CLOCK $c period=[get_property PERIOD $c]"
}

# Module-presence guard.  A register driven from two always blocks makes
# synthesis keep the constant driver and ignore the other (CRITICAL WARNING
# [Synth 8-6858]); that silently pruned the whole order book once.  Count the
# sequential cells inside each RTL module and fail loudly if a module is
# unexpectedly empty.
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
    error "MODULE-PRUNED: $tag has only $n sequential cells (< $min_ffs); \
look for CRITICAL WARNING [Synth 8-6858] multi-driven nets"
  }
}

# Connectivity guard for the MM2S memory path.  AXI interconnect exposes
# ARESETN plus one S*_ARESETN / M*_ARESETN per port; connect_bd_intf_net does
# NOT wire the per-port resets.  Unconnected per-port resets built, passed
# timing and passed every register-level check, yet left the interconnect
# held in reset so no MM2S read from DDR ever completed.  Assert the pins are
# actually driven here, before a bitstream can be emitted.
foreach {ic} {axi_mem_intercon} {
  foreach {pin} {S00_ARESETN M00_ARESETN S00_ACLK M00_ACLK} {
    set net [get_nets -quiet -of_objects [get_pins -quiet -hier -filter \
      "NAME =~ *${ic}/${pin}"]]
    if { $net eq "" } {
      error "CONNECTIVITY-FAIL: ${ic}/${pin} is not connected (AXI memory \
path would hang on hardware)"
    }
    puts "CONNECTIVITY: ${ic}/${pin} -> $net"
  }
}

# Reset-domain check.  Each per-port reset must be synchronous to its own
# port clock; a mismatched pair raises [BD 41-1343]/[BD 41-1348] at BD
# validation and was also what made two earlier naive fixes wrong.
#   S00_ACLK = clk_200m -> S00_ARESETN from rst_fclk0 (periph_aresetn)
#   M00_ACLK = fclk0    -> M00_ARESETN from the FCLK_CLK0-synchronous
#                          synchroniser (rst_hp2_port -> hp2_port_aresetn)
set m00_rst_net [get_nets -quiet -of_objects [get_pins -quiet -hier -filter \
  "NAME =~ *axi_mem_intercon/M00_ARESETN"]]
if { [string match "*hp2_port_aresetn*" $m00_rst_net] == 0 } {
  error "CONNECTIVITY-FAIL: axi_mem_intercon/M00_ARESETN ($m00_rst_net) is
not on the FCLK_CLK0-synchronous reset (expected hp2_port_aresetn)"
}
puts "CONNECTIVITY-OK: axi_mem_intercon per-port resets synchronous to port clocks"

set wns [get_property SLACK [get_timing_paths -delay_type max]]
set whs [get_property SLACK [get_timing_paths -delay_type min]]
set tns 0.0
set whs_paths [get_timing_paths -delay_type min -max_paths 1]
puts "WNS: $wns"
puts "WHS: $whs"

# Worst negative slack total (sum of all violated endpoints) — from the
# timing summary, which is authoritative for TNS.  The data line directly
# after the "WNS(ns) TNS(ns) ..." header starts with the WNS/TNS pair.
report_timing_summary -file [file join $REPO vivado timing_summary.rpt] -warn_on_violation
set fh [open [file join $REPO vivado timing_summary.rpt] r]
set summary_txt [read $fh]
close $fh
if { [regexp -line {^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s+(-?\d+\.\d+)} $summary_txt -> s_wns s_tns s_whs] } {
  puts "TNS: $s_tns"
  puts "TIMING-METRICS: WNS=$s_wns WHS=$s_whs TNS=$s_tns"
  # The live query (L142) and the summary (L156) are two independent sources for the same number.
  # Nothing compared them until round 244: print both so a build log can be checked for agreement.
  set wns_diff [expr {abs(double($wns) - double($s_wns))}]
  puts "TIMING-SOURCES: live=$wns summary=$s_wns diff=$wns_diff"
  if { $wns_diff > 0.002 } {
    puts "WARNING: TIMING-SOURCES-DISAGREE live=$wns summary=$s_wns (a build this large a gap means one is stale)"
  }
} else {
  puts "TNS: (unparsed)"
  puts "TIMING-METRICS: WNS=$wns WHS=$whs"
}

if { $wns < 0 } {
  # Emit the worst paths so the next iteration has data without re-running.
  report_timing_summary -file [file join $REPO vivado timing_fail_summary.rpt] -warn_on_violation
  report_timing -delay_type max -max_paths 20 -nworst 5 \
    -file [file join $REPO vivado timing_fail_paths.rpt]
  error "TIMING-FAIL: WNS = $wns (< 0) at the 190 MHz design clock"
}

file mkdir $OUT

# .bit from impl_1 run (official flow)
set bit_src [file join $WS nasdaq nasdaq.runs impl_1 nasdaq_wrapper.bit]
file copy -force $bit_src [file join $OUT nasdaq.bit]

# .hwh from BD hw_handoff (official flow)
set hwh_src [file join $WS nasdaq nasdaq.gen sources_1 bd nasdaq hw_handoff nasdaq.hwh]
file copy -force $hwh_src [file join $OUT nasdaq.hwh]

# Pair-completeness gate (FR-001): fail if either artifact is missing/empty
foreach f [list [file join $OUT nasdaq.bit] [file join $OUT nasdaq.hwh]] {
  if { ![file exists $f] || [file size $f] == 0 } {
    error "BUILD-FAIL: missing or empty artifact: $f"
  }
}

puts "BUILD-OVERLAY-OK bit+hwh emitted to $OUT"
