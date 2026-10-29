#!/usr/bin/env python3
"""Filter a raw ITCH 5.0 stream to a single stock_locate.

The PL order book builds one book for one stock, but the public feed is the
whole market.  This script produces a deterministic single-stock subset
(keeping the 2-byte length-prefixed message framing) that can be fed to the
hardware or to the CPU baseline.

Usage:
    python scripts/filter_itch_stock.py --input data/itch_1m.raw \
        --output data/itch_loc6836.raw --stock-locate 6836
"""

import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="Filter raw ITCH by stock_locate.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--stock-locate", type=int, required=True)
    args = ap.parse_args()

    data = open(args.input, "rb").read()
    out = bytearray()
    kept = seen = 0
    off = 0
    while off + 2 <= len(data):
        body_len = int.from_bytes(data[off:off + 2], "big")
        nxt = off + 2 + body_len
        if nxt > len(data):
            break
        body = data[off + 2:nxt]
        seen += 1
        if len(body) >= 3 and int.from_bytes(body[1:3], "big") == args.stock_locate:
            out += data[off:nxt]
            kept += 1
        off = nxt

    if kept == 0:
        print(f"ERROR: no messages for stock_locate {args.stock_locate}",
              file=sys.stderr)
        return 1

    with open(args.output, "wb") as f:
        f.write(out)
    print(f"FILTER-OK: kept {kept}/{seen} messages for stock_locate "
          f"{args.stock_locate}, {len(out)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
