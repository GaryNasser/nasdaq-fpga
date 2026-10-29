# Minimal Vivado smoke test: part check -> synth -> impl -> bitstream
set part    xc7z020clg400-1
set top     smoke_top
set outdir  [file normalize [file join [pwd] out]]

puts "===== Vivado smoke test ====="
puts "vivado : [version -short]"
puts "part   : $part"
puts "top    : $top"

file mkdir $outdir

# 1) Confirm the target device is present in this installation
set found [get_parts -quiet $part]
if {[llength $found] == 0} {
    puts "SMOKE_FAIL: part $part not found"
    exit 1
}
puts "part found: $found"

# 2) Read sources
read_verilog [file join [pwd] smoke_top.v]
read_xdc     [file join [pwd] smoke_top.xdc]

# 3) Full back-end flow
synth_design -top $top -part $part
opt_design
place_design
route_design

# 4) Reports
report_utilization    -file [file join $outdir utilization.rpt]
report_timing_summary -file [file join $outdir timing_summary.rpt]
report_drc            -file [file join $outdir drc.rpt]

# 5) Bitstream
write_bitstream -force [file join $outdir $top.bit]

set wsns [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
puts "worst setup WNS = $wsns ns"
puts "SMOKE_FLOW_DONE"