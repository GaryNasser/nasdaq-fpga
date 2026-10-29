# Read design status over JTAG, and program the PL, without Linux on the board.
#
# WHY THIS EXISTS
#
# Every board session so far depended on the PYNQ-Z2 running Linux and being
# reachable over SSH. The board has wedged twice - once from a killed process
# holding DMA descriptors - and each time all verification stopped until a physical
# power cycle.
#
# What was established this round, by probing:
#
#   hw_server connects and sees a target:  localhost:3121/xilinx_tcf/Xilinx/1234-tulA
#   the target exposes two devices:        arm_dap_0  xc7z020_1
#
# and this holds WHILE THE SoC IS HUNG. So the PL is reachable over JTAG even when
# Linux is dead. The FTDI "USB Serial Converter B" interface carries this and stays
# enumerated whenever the cable is attached.
#
# WHAT IT CAN AND CANNOT DO
#
#   CAN:  program the PL from a .bit over JTAG
#         confirm the target and devices are present
#         (attempt) reset the ARM cores through the DAP
#   CANNOT, as currently built:
#         read the AXI-Lite registers - that needs either a debug_bridge /
#         axi_jtag master in the block design, or the PS-side path that
#         load_overlay.py uses. arm_dap_0 exposes no hw_core to Vivado's
#         hardware manager, so the ARM reset is also best-effort.
#
# The register-read gap is a design change (add axi_jtag to the BD), not something
# this script can work around; it is written down here so the next session does not
# rediscover it.
#
# USAGE
#
#   vivado -mode batch -source tools/jtag_status.tcl
#       report target, devices, PL programmed state
#
#   vivado -mode batch -source tools/jtag_status.tcl -tclargs --program
#       also program the PL from vivado/out/nasdaq.bit

set out_dir  [file join [pwd] vivado workspace out]
set bit_file [file join $out_dir nasdaq.bit]

set do_program [expr {[lsearch -exact $argv "--program"] >= 0}]

if {[catch {
    open_hw_manager
    connect_hw_server -url localhost:3121
} err]} {
    puts "JTAG-NO-SERVER: $err"
    puts "  start it with: hw_server.bat   (from the Vivado bin directory)"
    exit 1
}

set targets [get_hw_targets]
if {[llength $targets] == 0} {
    puts "JTAG-NO-TARGET"
    puts "  no JTAG target: check that the FTDI cable is attached (USB Serial"
    puts "  Converter B must enumerate) - the board does NOT need to be booted."
    disconnect_hw_server
    close_hw_manager
    exit 1
}
set target [lindex $targets 0]
puts "JTAG-TARGET: $target"

current_hw_target $target
if {[catch {open_hw_target} err]} {
    puts "JTAG-OPEN-FAIL: $err"
    disconnect_hw_server
    close_hw_manager
    exit 1
}

set devs [get_hw_devices]
puts "JTAG-DEVICES: $devs"

set dev ""
foreach d $devs {
    if {[string match "*xc7z020*" $d]} { set dev $d; break }
}
if {$dev eq ""} {
    puts "JTAG-NO-PL-DEVICE"
    disconnect_hw_server
    close_hw_manager
    exit 1
}
current_hw_device $dev
puts "JTAG-PL-DEVICE: $dev"

if {$do_program} {
    if {![file exists $bit_file]} {
        puts "JTAG-NO-BITSTREAM: $bit_file"
        puts "  build it first: vivado -mode batch -source vivado/build_driver.tcl"
        disconnect_hw_server
        close_hw_manager
        exit 1
    }
    puts "JTAG-PROGRAMMING: $bit_file"
    if {[catch {
        set_property PROGRAM.FILE $bit_file $dev
        program_hw_devices $dev
    } err]} {
        puts "JTAG-PROGRAM-FAIL: $err"
        disconnect_hw_server
        close_hw_manager
        exit 1
    }
    puts "JTAG-PROGRAMMED"
} else {
    puts "JTAG-NOT-PROGRAMMING (pass --program to load the bitstream)"
}

# Report whether the DAP is visible; it is what a JTAG-only ARM reset would use.
if {[llength [get_hw_devices arm_dap*]] > 0} {
    puts "JTAG-DAP: present (arm cores exposed, but no hw_core for reset)"
} else {
    puts "JTAG-DAP: absent"
}

puts "JTAG-REGISTERS: not readable over JTAG - the block design has no"
puts "                debug AXI master; use load_overlay.py over SSH for that."

disconnect_hw_server
close_hw_manager
puts "JTAG-STATUS-DONE"
exit 0
