# A9 software baseline (B1)

`itch_book_baseline.c` is the CPU reference for the FPGA market-data
pipeline.  It decodes the same ITCH 5.0 messages and maintains an order book
with **exactly the semantics of `rtl/itch/order_book.v`**, so the throughput
comparison measures the same work on the same data.

## Semantics mirrored from the RTL

| Item | Behaviour |
| --- | --- |
| `order_map` | direct-mapped, index = `order_ref[11:0]`, tag = `order_ref[63:12]` |
| `level_table` | linear array, matched by **price only** (the RTL level entry has no side bit), usable indices `0..254`, linear search from 0 on every ADD |
| ADD | duplicate `order_ref` → drop; else reuse a same-price level (`shares +=`, `count += 1`) or allocate the next free level |
| EXECUTE / CANCEL | map hit required; level `shares -= shares`, level invalidated when depleted; the order is removed from `order_map` entirely (no per-order partial-fill tracking) |
| DELETE | map hit required; only the `order_map` entry is invalidated, level shares unchanged |
| REPLACE | map hit required; old `order_map` entry invalidated, new order not inserted (the RTL `ST_LEV_UPDATE` has no `ACT_REPLACE` arm) |
| DIRECTORY | no book effect |
| Side on non-ADD | `itch_parse` leaves the side bit at 0 for every non-ADD message, so EXECUTE/CANCEL always take the bid branch — mirrored here |

These are deliberate simplifications of the current RTL and are documented
in the final report; the baseline is *not* a full ITCH book.

## Build and run on the board

```sh
gcc -O3 -march=armv7-a -mfpu=neon -mfloat-abi=hard \
    -o itch_book_baseline itch_book_baseline.c
./itch_book_baseline --input data/itch_1m.raw --raw        # bare ITCH stream
./itch_book_baseline --input data/itch_1m.mold64           # MoldUDP64 stream
./itch_book_baseline --input data/itch_loc6836.raw --raw --max 100000
```

`--input` is required; `--raw` selects the bare 2-byte length-prefixed ITCH
stream (default is the project MoldUDP64 layout: 8-byte session + 2-byte
sequence + 2-byte count per packet — the same layout `scripts/pack_itch.py`
writes and `rtl/itch/mold64_reasm.v` expects).  `--max` caps the message
count.

Output is machine-parseable:

```
BASELINE-RESULT: msgs=... bytes=... elapsed_ns=... ns_per_msg=... msg_per_s=...
BOOK-COUNTERS: add=... exe=... can=... del=... rep=... drop=... orders=... levels=...
BBO: bid_price=... bid_shares=... bid_valid=... ask_price=... ask_shares=... ask_valid=...
BASELINE-DONE
```

`BOOK-COUNTERS` matches the RTL AXI4-Lite counters
(`BOOK_ADD_CNT` … `BOOK_DROP_CNT`, `BOOK_ORDER_CNT`, `BOOK_LEVEL_CNT`) so the
two implementations can be diffed directly.
