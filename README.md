# NASDAQ-FPGA

A hardware accelerator for NASDAQ TotalView-ITCH 5.0 market data on a
**PYNQ-Z2 (Zynq-7020)**. The whole feed path — MoldUDP64 frame reassembly, ITCH
5.0 message parsing, single-stock order-book maintenance, and latency
histogramming — runs in hand-written Verilog in the programmable logic. The ARM
cores only inject the capture over AXI DMA and read the result registers back.

The design closes timing at 190 MHz and reproduces a software reference exactly:
1,000,000 messages parsed with 0 gaps and 0 errors in simulation, and 43,428
messages replayed on the board with all eight order-book counters equal to the
C reference (`GOLDEN-OK`).

## Results

| Metric | Value |
| --- | --- |
| Design clock | 190 MHz — WNS **+0.094 ns**, WHS +0.012 ns, **0** of 18,529 endpoints failing |
| Resources | 4,524 LUT (8.5%), 5,437 FF (5.1%), 14 BRAM (10.0%), **0 DSP** |
| Throughput, PL pipeline | **299.01 ns/message → 3,344,390 msg/s** |
| Throughput, board end-to-end | **2,211,521 msg/s** (driver + AXI DMA) |
| A9 software baseline | 927.35 ns/message → 1,078,347 msg/s |
| Speed-up vs. A9 | **3.10×** |
| T1 latency (parse → book commit) | p50 **210.5 ns**, p95 **1,052.6 ns**, p99 **1,178.9 ns** (19,969 samples) |
| Correctness, simulation | 1,000,000 messages / 20,042 packets / 0 gap / 0 error; 171,945 messages over six stocks with 48/48 counters matching |
| Correctness, board | 850/850 packets, 43,428/43,428 messages, 8/8 counters matching |

## Architecture

```
 PS: ARM Cortex-A9 @ 650 MHz            PL: Zynq-7020 fabric @ 190 MHz
+------------------------------+      +--------------------------------------------+
| DDR3 capture buffer          |      |  mold64_reasm -> itch_parse -> order_book  |
| PYNQ overlay driver          | HP2  |        |             |            |       |
| (AXI DMA, MM2S 64-bit)       |=====>|  4 KB  |     event    |   commit   |       |
|                              |      |  ring  |   interface  |            |       |
| AXI4-Lite control/readback   |<---->|  ts_hist  (t1 - t0)  <---+            |       |
+------------------------------+ GP0  |  ctrl_regs: 5 AXI4-Lite slaves             |
                                      +--------------------------------------------+
```

* **`mold64_reasm`** — a true byte-FIFO (4 KB ring) that recovers message
  boundaries from the session name, 64-bit sequence number and 2-byte length
  prefix, and counts gaps and errors.
* **`itch_parse`** — one byte per cycle; a type table selects the field layout
  and extracts order reference, price, shares and side.
* **`order_book`** — 4,096-entry direct-mapped order table plus a 256-level price
  table; maintains add / execute / cancel / delete / replace and the best bid and
  offer.
* **`ts_hist`** — latches a free-running timestamp at the parser input (`t0`) and
  at book commit (`t1`), and accumulates the delta into a 256-bucket histogram
  along with count, min, max, sum and overflow.

Everything in the PL — including the AXI4-Lite control plane — runs on the
190 MHz clock from `clk_wiz_0`. The only clock-domain crossing is inside the HP2
memory interconnect (`auto_cc`, 100 ↔ 190 MHz).

## Repository layout

| Path | Contents |
| --- | --- |
| `rtl/itch/` | `mold64_reasm.v`, `itch_parse.v`, `order_book.v`, `ts_hist.v` and their testbenches |
| `rtl/` | `ctrl_regs.v` (AXI4-Lite register file), `loopback_dma.v` (DMA bootstrap stub) |
| `vivado/` | `create_project.tcl` builds the project and block design; further Tcl for synthesis, implementation and reports; timing constraints |
| `tools/` | Simulation testbenches (`tb_*.v`), the suite runner, the contract-check suite, and the real-capture replay harness |
| `board/` | `load_overlay.py` — PYNQ overlay load, DMA replay and golden-counter comparison; `probe_debug.py` |
| `sw/baseline/` | The C reference order book that defines the golden counters |
| `sw/net/` | Capture and UDP replay utilities |
| `scripts/` | Fetch and truncate an ITCH development subset, filter by stock, pack captures, run the Windows build/deploy flows |
| `smoke/` | A minimal synthesis flow for bring-up |

## Building

Requires **Vivado 2024.1**.

```bash
vivado -mode batch -source vivado/build_driver.tcl
```

`build_driver.tcl` sources `create_project.tcl` (project + block design) and then
`build_overlay.tcl` (synthesis, implementation, `.bit` + `.hwh`) **in one session**
— the out-of-context synthesis runs are registered in the session that generated
them, so splitting them across two `vivado` invocations silently loses them.

The output pair lands in `vivado/out/`. On Windows `scripts/build.ps1` runs the
simulation gate before the build; it hard-codes the Vivado path, so adjust that
line for your install.

## Verification

Three independent layers, all runnable from the repository root:

```bash
python tools/run_checks.py     # 301 static contract checks (no simulator needed)
python tools/run_sims.py       # 37 behavioural suites under xsim
python tools/run_realfile.py   # real captured traffic through the reassembler
```

* **`run_checks.py`** guards the class of defect that only shows up on hardware:
  a wrong clock constant, a FIFO depth that evaluated 50% high, latency reported
  in cycles as nanoseconds, a driver that had never executed.
* **`run_sims.py`** runs the xsim suites one `xvlog`/`xelab`/`xsim` triad at a
  time and reports a single verdict per suite. Some suites are *expected* to fail
  — they pin down a documented limitation, so a fix would make them report
  otherwise.
* **`run_realfile.py`** replays an actual capture and compares the design's
  counters against an independent MoldUDP64 parse of the same file.

## Running on the board

Deploy the bitstream and driver to the PYNQ board, then replay a capture:

```bash
scp vivado/out/nasdaq.bit vivado/out/nasdaq.hwh board/load_overlay.py \
    xilinx@<board>:/home/xilinx/overlays/nasdaq/

ssh xilinx@<board> 'cd /home/xilinx/overlays/nasdaq && \
  sudo -n env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python load_overlay.py \
  --book --input /home/xilinx/<capture>.mold64'
```

All three conditions in that command are required on PYNQ: the venv interpreter
(the system `python3` has no `pynq`), `sudo -n` (`/dev/mem` access needs root),
and `XILINX_XRT=/usr` (sudo strips the environment). Expected output ends with:

```
M64-STATS:  rx_packets=850 rx_messages=43428 gap=0 err=0
TS-STATS:   count=19969 ... p50_ns=210.5 p95_ns=1052.6 p99_ns=1178.9 overflow=0
GOLDEN-OK:  all 8 book counters match the A9 baseline
```

## Market data

The captures used for testing are **not** redistributed here. Nasdaq publishes a
sample ITCH 5.0 feed; `scripts/fetch_itch.py` streams it, truncates at a chosen
message count and writes a packed `.mold64` file, and `scripts/pack_itch.py`
converts raw ITCH into the length-prefixed pack the DMA replay expects. Any
MoldUDP64 capture works — the counters will simply differ.

## Known limitations

* One stock at a time. The 4,096-entry order table is direct-mapped and the price
  table holds 256 levels; a whole-market stream overflows both, and the `drop`
  counter reports it rather than hiding it. Per-stock sharding is the documented
  extension path.
* The DMA path is MM2S only. `S2MM` is not instantiated, so the order book cannot
  be written back to DDR.
* The PYNQ-Z2 routes its gigabit PHY to PS MIO, so the PL has no Ethernet pins
  and a line-rate PL capture front end is not possible on this board.
* DMA injection reaches 39.2 MB/s end to end through the driver, against
  62.3–62.8 MB/s for the pipeline itself; the gap is descriptor and driver
  overhead.
