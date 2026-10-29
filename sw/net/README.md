# M6 network capture path (partial)

The PYNQ-Z2 has no PL-side Ethernet: all packets arrive through the PS
(`eth0`), so the planned network mode is a PS-driven capture path.  These
tools exercise that path with the project MoldUDP64 framing:

| File | Role |
| --- | --- |
| `itch_capture.c` | AF_PACKET + `PACKET_MMAP` (`TPACKET_V2`) receiver; validates session/sequence/count framing and reports ring drops |
| `send_itch_udp.c` | C replay source (one UDP datagram per MoldUDP64 packet) |
| `send_itch_udp.py` | Python replay source (same framing, slower; useful for paced tests) |

## Build (on the board)

```sh
gcc -O3 -march=armv7-a -mfpu=neon -mfloat-abi=hard -o itch_capture itch_capture.c
gcc -O3 -march=armv7-a -mfpu=neon -mfloat-abi=hard -o send_itch_udp_c send_itch_udp.c
```

## Measured (PYNQ-Z2, armv7l, kernel 6.6.10)

Loopback test (`lo`, UDP port 9000), data set `itch_loc6836.mold64`
(850 packets / 43,428 messages per pass), receiver ring 16 × 256 KiB:

| Test | Injected | Captured packets | Captured messages | Ring drops |
| --- | --- | --- | --- | --- |
| 1 C sender | 17,000 pkt (193 Mbps, 1.02 s) | 17,000 | 868,560 | **0** |
| 2 C senders | 34,000 pkt (~239 Mbps aggregate) | 34,000 | 1,737,120 | **0** |

Packet and message counts match the injected traffic exactly, and the
MoldUDP64 session/framing validation reported 0 malformed packets.

## Scope / non-claims

* **This is not K1.** K1 asks for 1 GbE line rate with zero PL-side drops.
  Here the bytes never enter the PL: the receiver is a userspace ring, and
  the overlay's S2MM path is not wired to this ring.  Wiring it would need
  a DMA ring (or a PL AXI-Stream input) added to the block design.
* The measured rate is bounded by the **sender**, not the receiver: a
  650 MHz Cortex-A9 issuing one `sendto()` per ~1.4 KB datagram saturates at
  roughly 10–17 k pkt/s per core.  Reaching 1 Gbps with ITCH-sized packets
  needs ~87 k pkt/s, which is itself a finding for the PS-only entry path.
* T2 (wire-to-book latency) therefore remains unmeasured; see
  `docs/final-report.md` §6 and §8.
