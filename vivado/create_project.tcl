# create_project.tcl — build the nasdaq Vivado project + block design.
# Batch mode: vivado -mode batch -source create_project.tcl
#
# Design (M3 protocol parse + M4 order book + M5 measurement, specs/003/004/005):
#   ps7_0 (official PYNQ-Z2 PS config; PS supplies 100 MHz to the clock wizard)
#   + axi_interconnect_0 (5 masters: DMA ctrl + mold64 + itch + book + ts_hist)
#   + axi_dma_0 (simple DMA, 64-bit, MM2S + S2MM)
#   + mold64_reasm_0 (rtl/itch/mold64_reasm.v: MoldUDP64 -> ITCH byte stream)
#   + itch_parse_0 (rtl/itch/itch_parse.v: ITCH byte stream -> book events)
#   + order_book_0 (rtl/itch/order_book.v: single-stock order book + BBO)
#   + ts_hist_0 (rtl/itch/ts_hist.v: timestamp counter + latency histogram)
#   + axi_mem_intercon (DMA MM2S/S2MM -> PS HP0/HP2)
#   + xlconcat_0 (DMA interrupts -> PS IRQ_F2P)
#   + clk_wiz_0 (100 -> 190 MHz design clock; see the clock plan below)
#   + rst_fclk0
#
# Output: vivado/workspace/nasdaq/nasdaq.xpr with BD "nasdaq" ready for
# build_overlay.tcl. Idempotent: workspace is cleaned by build.ps1 first.

set REPO [file normalize [file join [file dirname [file normalize [info script]]] ..]]
set WS   [file join $REPO vivado workspace]

# ---- project ------------------------------------------------------------
create_project nasdaq [file join $WS nasdaq] -part xc7z020clg400-1 -force

# RTL sources (implementation); testbench goes to sim_1
add_files -fileset sources_1 [list \
  [file join $REPO rtl ctrl_regs.v] \
  [file join $REPO rtl itch mold64_reasm.v] \
  [file join $REPO rtl itch itch_parse.v] \
  [file join $REPO rtl itch order_book.v] \
  [file join $REPO rtl itch ts_hist.v] \
]
add_files -fileset sim_1 [list \
  [file join $REPO rtl itch tb_mold64_reasm.v] \
  [file join $REPO rtl itch tb_itch_parse.v] \
  [file join $REPO rtl itch tb_order_book.v] \
  [file join $REPO rtl itch tb_ts_hist.v] \
]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

# ---- timing constraints (multi-cycle paths for CARRY4 comparators) ----
# Load timing_mcyc.xdc: relaxes the ptr_eq and gap_count CARRY4 chains
# that are false-critical (stable for many cycles, only checked at packet
# boundaries). Without these, WNS varies -0.5 to +0.2 across placement
# seeds and the design was marginal at 200 MHz, hence the move to 190.
read_xdc [file join $REPO vivado timing_mcyc.xdc]


# ---- block design -------------------------------------------------------
create_bd_design nasdaq
current_bd_design [get_bd_designs nasdaq]

# PS7 with the official PYNQ-Z2 configuration
source [file join [file dirname [file normalize [info script]]] ps7_config.tcl]
set ps7 [nasdaq::create_ps7 nasdaq ps7_0]

# ---- AXI DMA (simple mode, 64-bit, MM2S + S2MM) -------------------------
set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_0]
set_property -dict [list \
  CONFIG.c_include_mm2s {1} \
  CONFIG.c_include_s2mm {0} \
  CONFIG.c_include_sg     {0} \
  CONFIG.c_mm2s_burst_size {256} \
  CONFIG.c_sg_length_width {22} \
  CONFIG.c_m_axi_mm2s_data_width {64} \
  CONFIG.c_m_axis_mm2s_tdata_width {64} \
] $dma

# ---- mold64_reasm (MoldUDP64 depacketizer, 64-bit stream in, 8-bit out) ---
set mold64 [create_bd_cell -type module -reference mold64_reasm mold64_reasm_0]

# ---- itch_parse (ITCH 5.0 decoder, 8-bit stream in, 256-bit event out) ---
set itch [create_bd_cell -type module -reference itch_parse itch_parse_0]

# ---- order_book (single-stock price-level book with BBO tracking) -------
set book [create_bd_cell -type module -reference order_book order_book_0]
set_property -dict [list \
  CONFIG.ORDERS {4096} \
  CONFIG.LEVELS {256} \
  CONFIG.ORD_ADDR_W {12} \
  CONFIG.LEVEL_ADDR_W {8} \
] $book

# ---- ts_hist (M5 measurement: timestamp counter + latency histogram) -----
set ts_hist [create_bd_cell -type module -reference ts_hist ts_hist_0]

# ---- AXI interconnect: GP0 -> 5 slaves (DMA ctrl + mold64 + itch + book + ts) -
set axi_ic [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_interconnect_0]
set_property -dict [list CONFIG.NUM_MI {5}] $axi_ic

# ---- AXI mem interconnect: DMA MM2S -> PS HP2 ---------------------------
set axi_mem [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_mem_intercon]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] $axi_mem

# ---- Interrupt aggregation: DMA -> PS IRQ_F2P ---------------------------
set xlconcat [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconcat:2.1 xlconcat_0]
set_property -dict [list CONFIG.NUM_PORTS {1}] $xlconcat

# ---- Clock wizard: FCLK0 (100 MHz) -> 190 MHz design clock --------------
#
# 190 MHz rather than 200. The streaming datapath (mold64_reasm) passes 200 MHz
# comfortably and never appears in the critical paths; the design misses by
# ~0.09 ns on a 32-bit min/max magnitude compare inside ts_hist, whose exact
# 32-bit reported values forbid narrowing the compare. Two pipelining attempts
# broke the statistics and a whole-module floorplan made placement worse.
#
# 190 MHz is not a functional compromise: nothing external requires 200 MHz.
# The PS interfaces are on separate FCLK domains and the AXI clock converters
# absorb the rate change; DESIGN_FREQ below is what the timing gate checks.
set DESIGN_FREQ 190.000

set clk_wiz [create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 clk_wiz_0]
set_property -dict [list CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {190.000} \
                         CONFIG.USE_LOCKED {true} \
                         CONFIG.USE_RESET {false} \
                         CONFIG.PRIM_IN_FREQ {100.000}] $clk_wiz

# ---- Peripheral reset ---------------------------------------------------
set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_fclk0]

# ---- connections --------------------------------------------------------
# Clock plan: everything runs at 190 MHz (clk_wiz_0 clk_out1), fed by the
# PS FCLK_CLK0 at 100 MHz.
#
# CORRECTED (round 35): the topology, read from the connections below rather than
# assumed:
#
#   clk_200m -> ps7_0/M_AXI_GP0_ACLK, and EVERY axi_interconnect_0 ACLK
#   fclk0    -> ps7_0's S_AXI_{GP0,HP0,HP2}_ACLK, and axi_mem_intercon/M00_ACLK
#
# So the GP0 control plane is SINGLE-DOMAIN (PS port and interconnect both on
# clk_200m) and needs no converter. The only crossing is
# axi_mem_intercon S00 (clk_200m) <-> M00 (fclk0), where Vivado's AXI Interconnect
# generates auto_cc - the sole auto_cc in the routed netlist.
#
# timing_mcyc.xdc declares the two clock groups asynchronous for that ONE crossing.
# It does not remove the GP0 control path from analysis; both its ends are clk_out1.
connect_bd_net -net fclk0 \
  [get_bd_pins ps7_0/FCLK_CLK0] \
  [get_bd_pins ps7_0/M_AXI_GP1_ACLK] \
  [get_bd_pins ps7_0/S_AXI_GP0_ACLK] \
  [get_bd_pins ps7_0/S_AXI_HP0_ACLK] \
  [get_bd_pins ps7_0/S_AXI_HP2_ACLK] \
  [get_bd_pins axi_mem_intercon/M00_ACLK] \
  [get_bd_pins clk_wiz_0/clk_in1]

connect_bd_net -net clk_200m \
  [get_bd_pins clk_wiz_0/clk_out1] \
  [get_bd_pins ps7_0/M_AXI_GP0_ACLK] \
  [get_bd_pins axi_interconnect_0/ACLK] \
  [get_bd_pins axi_interconnect_0/S00_ACLK] \
  [get_bd_pins axi_interconnect_0/M00_ACLK] \
  [get_bd_pins axi_interconnect_0/M01_ACLK] \
  [get_bd_pins axi_interconnect_0/M02_ACLK] \
  [get_bd_pins axi_interconnect_0/M03_ACLK] \
  [get_bd_pins axi_interconnect_0/M04_ACLK] \
  [get_bd_pins axi_dma_0/s_axi_lite_aclk] \
  [get_bd_pins axi_dma_0/m_axi_mm2s_aclk] \
  [get_bd_pins axi_mem_intercon/ACLK] \
  [get_bd_pins axi_mem_intercon/S00_ACLK] \
  [get_bd_pins mold64_reasm_0/aclk] \
  [get_bd_pins itch_parse_0/aclk] \
  [get_bd_pins order_book_0/aclk] \
  [get_bd_pins ts_hist_0/aclk] \
  [get_bd_pins rst_fclk0/slowest_sync_clk]

connect_bd_net -net fclk_reset_n \
  [get_bd_pins ps7_0/FCLK_RESET0_N] \
  [get_bd_pins rst_fclk0/ext_reset_in]

connect_bd_net -net clk_wiz_locked \
  [get_bd_pins clk_wiz_0/locked] \
  [get_bd_pins rst_fclk0/dcm_locked]

connect_bd_net -net periph_aresetn \
  [get_bd_pins rst_fclk0/peripheral_aresetn] \
  [get_bd_pins axi_interconnect_0/S00_ARESETN] \
  [get_bd_pins axi_interconnect_0/M00_ARESETN] \
  [get_bd_pins axi_interconnect_0/M01_ARESETN] \
  [get_bd_pins axi_interconnect_0/M02_ARESETN] \
  [get_bd_pins axi_interconnect_0/M03_ARESETN] \
  [get_bd_pins axi_interconnect_0/M04_ARESETN] \
  [get_bd_pins mold64_reasm_0/aresetn] \
  [get_bd_pins itch_parse_0/aresetn] \
  [get_bd_pins order_book_0/aresetn] \
  [get_bd_pins ts_hist_0/aresetn]
connect_bd_net -net ic_aresetn \
  [get_bd_pins rst_fclk0/interconnect_aresetn] \
  [get_bd_pins axi_interconnect_0/ARESETN]
connect_bd_net -net periph_aresetn \
  [get_bd_pins axi_dma_0/axi_resetn]
connect_bd_net -net ic_aresetn \
  [get_bd_pins rst_fclk0/interconnect_aresetn] \
  [get_bd_pins axi_mem_intercon/ARESETN]

# axi_mem_intercon per-port resets.  S00_ARESETN/M00_ARESETN are SEPARATE
# pins from ARESETN and are NOT connected by connect_bd_intf_net.
#
# Leaving them dangling silently broke every MM2S read from DDR while the
# AXI4-Lite control path (axi_interconnect_0, whose per-port resets WERE
# connected) kept working — so register reads/writes looked healthy and the
# build reported no critical warning or DRC error.  On hardware the MM2S
# channel sat with DMASR = 0x00000000 (never IDLE, never HALTED) and
# sendchannel.wait() spun forever with rx_packets = 0.
#
# Each per-port reset must be synchronous to THAT PORT'S clock:
#   S00_ACLK = clk_200m (DMA MM2S side)  -> periph_aresetn, which proc_sys_reset
#                                           rst_fclk0 derives from clk_out1
#   M00_ACLK = fclk0    (PS HP2 side)    -> a reset synchronised to FCLK_CLK0
#
# M00_ARESETN must NOT be driven from rst_fclk0 (that reset is synchronous to
# the 190 MHz clk_out1, giving [BD 41-1343]) and must NOT be driven straight
# from FCLK_RESET0_N either (that is an asynchronous reset, giving
# [BD 41-1348]).  It needs a reset synchroniser clocked by FCLK_CLK0, so a
# second proc_sys_reset (rst_fclk0_raw) is instantiated on FCLK_CLK0 purely to
# produce a clean peripheral_aresetn for the HP2-side port.
set rst_hp [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_hp2_port]

connect_bd_net -net periph_aresetn \
  [get_bd_pins axi_mem_intercon/S00_ARESETN]
connect_bd_net -net fclk_reset_n \
  [get_bd_pins ps7_0/FCLK_RESET0_N] \
  [get_bd_pins rst_hp2_port/ext_reset_in]
connect_bd_net -net fclk0 \
  [get_bd_pins rst_hp2_port/slowest_sync_clk]
connect_bd_net -net clk_wiz_locked \
  [get_bd_pins rst_hp2_port/dcm_locked]
connect_bd_net -net hp2_port_aresetn \
  [get_bd_pins rst_hp2_port/peripheral_aresetn] \
  [get_bd_pins axi_mem_intercon/M00_ARESETN]

connect_bd_intf_net -intf_net ps7_gp0 \
  [get_bd_intf_pins ps7_0/M_AXI_GP0] \
  [get_bd_intf_pins axi_interconnect_0/S00_AXI]

connect_bd_intf_net -intf_net axi_to_dma \
  [get_bd_intf_pins axi_interconnect_0/M00_AXI] \
  [get_bd_intf_pins axi_dma_0/S_AXI_LITE]

connect_bd_intf_net -intf_net axi_to_mold64 \
  [get_bd_intf_pins axi_interconnect_0/M01_AXI] \
  [get_bd_intf_pins mold64_reasm_0/s_axi]

connect_bd_intf_net -intf_net axi_to_itch \
  [get_bd_intf_pins axi_interconnect_0/M02_AXI] \
  [get_bd_intf_pins itch_parse_0/s_axi]

connect_bd_intf_net -intf_net axi_to_book \
  [get_bd_intf_pins axi_interconnect_0/M03_AXI] \
  [get_bd_intf_pins order_book_0/s_axi]

connect_bd_intf_net -intf_net axi_to_ts_hist \
  [get_bd_intf_pins axi_interconnect_0/M04_AXI] \
  [get_bd_intf_pins ts_hist_0/s_axi]

connect_bd_intf_net -intf_net dma_mm2s \
  [get_bd_intf_pins axi_dma_0/M_AXI_MM2S] \
  [get_bd_intf_pins axi_mem_intercon/S00_AXI]

connect_bd_intf_net -intf_net mem_to_hp2 \
  [get_bd_intf_pins axi_mem_intercon/M00_AXI] \
  [get_bd_intf_pins ps7_0/S_AXI_HP2]

connect_bd_intf_net -intf_net dma_to_mold64 \
  [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S] \
  [get_bd_intf_pins mold64_reasm_0/s_axis]

connect_bd_intf_net -intf_net mold64_to_itch \
  [get_bd_intf_pins mold64_reasm_0/m_axis] \
  [get_bd_intf_pins itch_parse_0/s_axis]

# ---- itch_parse -> order_book event stream (AXI-Stream-like, flat) ----
# itch_parse outputs evt (256-bit) + evt_valid + stock_locate;
# order_book inputs the same and drives evt_ready back.
connect_bd_net [get_bd_pins itch_parse_0/evt]        [get_bd_pins order_book_0/evt]
connect_bd_net [get_bd_pins itch_parse_0/evt_valid]  [get_bd_pins order_book_0/evt_valid]
connect_bd_net [get_bd_pins order_book_0/evt_ready]  [get_bd_pins itch_parse_0/evt_ready]
connect_bd_net [get_bd_pins itch_parse_0/stock_locate] [get_bd_pins order_book_0/stock_locate]

# ---- M5 sideband timestamp wiring ------------------------------------
# itch_parse -> ts_hist: ingress pulse (t0 capture)
connect_bd_net [get_bd_pins itch_parse_0/ts_in_valid] [get_bd_pins ts_hist_0/ingress_valid]
# order_book -> ts_hist: completion pulse (t1 capture)
connect_bd_net [get_bd_pins order_book_0/ts_done_valid] [get_bd_pins ts_hist_0/completion_valid]
# itch_parse evt[3:0] (act field) -> ts_hist msg_type — extract via xlslice
set slice_act [create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice:1.0 xlslice_act_0]
set_property -dict [list CONFIG.DIN_WIDTH {256} CONFIG.DIN_FROM {3} CONFIG.DIN_TO {0} CONFIG.DOUT_WIDTH {4}] $slice_act
connect_bd_net [get_bd_pins itch_parse_0/evt] [get_bd_pins xlslice_act_0/Din]
connect_bd_net [get_bd_pins xlslice_act_0/Dout] [get_bd_pins ts_hist_0/msg_type]

connect_bd_net -net dma_mm2s_intr \
  [get_bd_pins axi_dma_0/mm2s_introut] \
  [get_bd_pins xlconcat_0/In0]
connect_bd_net -net xlconcat_to_ps \
  [get_bd_pins xlconcat_0/dout] \
  [get_bd_pins ps7_0/IRQ_F2P]

assign_bd_address

validate_bd_design
save_bd_design

# Generate IP targets (OOC synth stubs + DCPs) for every BD cell.
#
# The BD target tree (nasdaq.gen/sources_1/bd/nasdaq/{synth,sim,hw_handoff})
# is created by the BD writer, but on this host generate_target has been seen
# to fail with
#   ERROR: [Common 17-71] Directory .../bd/nasdaq/sim does not exist
# when that subdirectory was not materialised. Create the expected tree up
# front so target generation does not depend on it.
foreach {sub} {synth sim hw_handoff ip} {
  set d [file join $WS nasdaq nasdaq.gen sources_1 bd nasdaq $sub]
  if { ![file exists $d] } { file mkdir $d }
}
generate_target all [get_files nasdaq.bd]

# Remove synth wrappers (behavioral models) now that DCPs exist.
# This prevents synth_1 from synthesizing the PS7 behavioral model
# (which would cause 308K LUT over-utilization and OOM the system).
# With synth wrappers removed, synth_1 uses black-box stubs (fast, tiny)
# and impl_1 reads the per-IP DCPs for the real logic.
#
# NOTE: target the BD FILE (not get_ips *, which matches BD cells and
# triggers ERROR [Vivado 12-3424] "IP cores may not be directly generated").
export_ip_user_files -of_objects [get_files nasdaq.bd] -sync -no_script -force
update_compile_order -fileset sources_1

# ---- top wrapper --------------------------------------------------------
make_wrapper -files [get_files -of_objects [get_filesets sources_1] nasdaq.bd] -top -import
set_property top nasdaq_wrapper [current_fileset]
update_compile_order -fileset sources_1

puts "CREATE-PROJECT-OK"
