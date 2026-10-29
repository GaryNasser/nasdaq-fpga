"""Audit the project against the requirements in its own assignment statement.

docs/赛题陈述-修订版.md commits to a specific, checkable set of deliverables. This
extracts them and records the evidence state for each, so the report can state
plainly what is met, what is met in simulation only, and what is unmeasured.

The distinction matters because the assignment was itself rewritten to match the
real hardware - a reader is entitled to know which of the revised promises are now
backed by measurement and which are still promises.
"""
import io

PATH = r"C:\Users\qingx\AppData\Local\Temp\reqaudit.txt"

ROWS = [
    ("AXI-Stream 帧接入", "tb_fullchain / tb_fullchain_1m",
     "met (simulation)", "850/850 and 20042/20042 packets"),
    ("MoldUDP64 帧重组", "tb_realfile, tb_fullchain",
     "met (simulation)", "0 gaps, 0 errors, 1.2 MB and 29 MB captures"),
    ("ITCH 报文解析", "tb_book, tb_fullchain",
     "met (simulation)", "43428/43428 messages, 8/8 golden counters"),
    ("实现方式声明 (RTL vs HLS)",
     "repository scan: all .v, no pragma HLS, no HLS in the build tcl",
     "CORRECTED", "claimed RTL + Vitis HLS; there is no HLS in this project"),
    ("有界订单簿维护", "tb_book",
     "met (simulation)", "add/exe/can/del/rep/drop/orders/levels all match A9"),
    ("硬件时间戳与延迟直方图", "tb_fullchain (ts_hist enabled)",
     "met (simulation)", "19969 samples, p50 210.5 / p95 1052.6 / p99 1178.9 ns"),
    ("PS 经 AXI DMA 注入 (回放模式)", "board/load_overlay.py --book",
     "UNVERIFIED on hardware", "driver executes against a mock only; DMA never ran"),
    ("千兆线速不丢包 (网络模式)", "PS PACKET_MMAP capture",
     "UNVERIFIED (captured 239 Mbps / 0 loss, never wired to PL)", "K1"),
    ("PL 吞吐上限", "tb_rate_book",
     "met (simulation)", "3,344,390 msg/s, 94.5 MB/s, 299.01 ns/msg"),
    ("等效万兆能力论证", "derived from PL throughput vs 1 GbE",
     "PARTIAL", "PL 94.5 MB/s vs ~119 MB/s 1 GbE - NOT a 10x margin at this msg size"),
    ("tick-to-book P50/P95/P99 (T1)", "tb_fullchain",
     "met (simulation, PL-internal)", "210.5 / 1052.6 / 1178.9 ns"),
    ("tick-to-book 端到端 (T2)", "requires board",
     "UNMEASURED", "needs the board"),
    ("片上资源占用 LUT/FF/BRAM/DSP", "impl reports",
     "met", "from the routed build"),
    ("WNS 时序收敛", "impl report",
     "met", "WNS +0.127, WHS +0.031, 0/18384 failing at 190 MHz"),
    ("与 A9 基线实测加速比", "check_speedup.py",
     "met (PL-side, I/O confound measured at 2%)", "3.10x, conservative end of 3.10-4.73x"),
    ("可迁移至万兆 (>10x 余量)", "derived",
     "CONTRADICTED at this message size", "see below"),
]

lines = []
lines.append("assignment requirement audit")
lines.append("=" * 78)
met = unver = unmeas = contradicted = partial = corrected = 0
for req, how, state, detail in ROWS:
    lines.append("%-34s %s" % (req, state))
    lines.append("%-34s   evidence: %s" % ("", how))
    lines.append("%-34s   detail:   %s" % ("", detail))
    if state.startswith("met"):
        met += 1
    elif state.startswith("UNMEASURED"):
        unmeas += 1
    elif state.startswith("UNVERIFIED"):
        unver += 1
    elif state.startswith("CONTRADICTED"):
        contradicted += 1
    elif state.startswith("PARTIAL"):
        partial += 1
    elif state.startswith("CORRECTED"):
        corrected += 1

lines.append("")
lines.append("=" * 78)
lines.append("met: %d, partial: %d, corrected: %d, unverified-on-hardware: %d, "
             "unmeasured: %d, contradicted: %d"
             % (met, partial, corrected, unver, unmeas, contradicted))
lines.append("")
lines.append("THE CONTRADICTION")
lines.append("  The assignment claims the PL pipeline has '一个数量级以上的实测余量'")
lines.append("  (>10x) over the 1 GbE ingress. Measured PL throughput is 94.5 MB/s")
lines.append("  at 28 B/message. 1 GbE line rate is 125 MB/s (119 MB/s at TCP")
lines.append("  payload). That is 0.79x - the PL is SLOWER than the wire at this")
lines.append("  message size, not 10x faster.")
lines.append("")
lines.append("  At larger messages the ratio improves (throughput is per-message")
lines.append("  bound, not per-byte). The claim would hold for messages above")
lines.append("  roughly 350 B. But as written, for the ITCH distribution measured")
lines.append("  here, it is wrong and must be corrected rather than repeated.")

out = io.open(PATH, "w", encoding="utf-8")
out.write("\n".join(lines))
out.close()
print("\n".join(l for l in lines if l.isascii()))
