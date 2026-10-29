#!/usr/bin/env python3
"""ref_itch_parse.py: golden-reference ITCH 5.0 parser.

Reads a raw ITCH 5.0 binary file (concatenated 2-byte big-endian length-prefixed
messages) and decodes every message into structured JSON-line events.  This
script produces the "golden answer" that the RTL itch_parse module's output is
compared against.

Usage:
    python scripts/ref_itch_parse.py --input <raw_itch> --output <events.jsonl> [--max N]
"""

import argparse
import json
import struct
import sys


# ---------------------------------------------------------------------------
# ITCH 5.0 message type table
# ---------------------------------------------------------------------------
# Each entry: (type_byte, name, act_label, field_extractor_func).
# Body length (the value in the 2-byte prefix) includes the type byte at [0].

MSG_TYPE_A = 0x41  # Add Order (no MPID)
MSG_TYPE_F = 0x46  # Add Order (with MPID)
MSG_TYPE_E = 0x45  # Order Executed
MSG_TYPE_C = 0x43  # Order Executed With Price
MSG_TYPE_X = 0x58  # Order Cancel
MSG_TYPE_D = 0x44  # Order Delete
MSG_TYPE_U = 0x55  # Order Replace
MSG_TYPE_R = 0x52  # Stock Directory

KNOWN_TYPES = {
    MSG_TYPE_A, MSG_TYPE_F, MSG_TYPE_E, MSG_TYPE_C,
    MSG_TYPE_X, MSG_TYPE_D, MSG_TYPE_U, MSG_TYPE_R,
}

# Expected body lengths (including type byte) per the ITCH 5.0 spec.
EXPECTED_BODY_LEN = {
    MSG_TYPE_A: 36,
    MSG_TYPE_F: 40,
    MSG_TYPE_E: 31,
    MSG_TYPE_C: 36,
    MSG_TYPE_X: 23,
    MSG_TYPE_D: 19,
    MSG_TYPE_U: 35,
    MSG_TYPE_R: 39,
}


def decode_timestamp(body: bytes) -> int:
    """Decode a 48-bit (6-byte) big-endian nanosecond timestamp."""
    # 6 bytes -> pad to 8 for int.unpack; big-endian zero-extend.
    return int.from_bytes(body[0:6], "big")


def decode_stock(body: bytes) -> str:
    """Decode an 8-byte space-padded ASCII stock symbol."""
    return body[0:8].decode("ascii", errors="replace").rstrip(" ")


def parse_message(body: bytes) -> dict:
    """Decode one ITCH message body (type byte is body[0]) into a JSON event."""
    type_byte = body[0]

    # Common prefix fields present in every order book message.
    stock_locate = int.from_bytes(body[1:3], "big")
    tracking = int.from_bytes(body[3:5], "big")
    timestamp = decode_timestamp(body[5:11])

    # Base event with the fields every message shares.
    event = {
        "msg_type": chr(type_byte),
        "stock_locate": stock_locate,
        "tracking": tracking,
        "timestamp": timestamp,
    }

    if type_byte in (MSG_TYPE_A, MSG_TYPE_F):
        # Add Order: A (no MPID) and F (with MPID).
        order_ref = int.from_bytes(body[11:19], "big")
        side = chr(body[19])
        shares = int.from_bytes(body[20:24], "big")
        stock = decode_stock(body[24:32])
        event.update({
            "act": "add",
            "order_ref": order_ref,
            "side": side,
            "shares": shares,
            "stock": stock,
        })
        if type_byte == MSG_TYPE_A:
            event["price"] = int.from_bytes(body[32:36], "big")
        else:
            # 'F' has MPID at [32:36], price shifts to [36:40].
            event["mpid"] = body[32:36].decode("ascii", errors="replace").rstrip(" ")
            event["price"] = int.from_bytes(body[36:40], "big")

    elif type_byte in (MSG_TYPE_E, MSG_TYPE_C):
        # Order Executed / Executed With Price.
        order_ref = int.from_bytes(body[11:19], "big")
        shares = int.from_bytes(body[19:23], "big")
        match_id = int.from_bytes(body[23:31], "big")
        event.update({
            "act": "execute",
            "order_ref": order_ref,
            "shares": shares,
            "match_id": match_id,
        })
        if type_byte == MSG_TYPE_C:
            # Executed With Price adds a 4-byte price at [27:35].
            event["price"] = int.from_bytes(body[27:31], "big")

    elif type_byte == MSG_TYPE_X:
        # Order Cancel.
        order_ref = int.from_bytes(body[11:19], "big")
        shares = int.from_bytes(body[19:23], "big")
        event.update({
            "act": "cancel",
            "order_ref": order_ref,
            "shares": shares,
        })

    elif type_byte == MSG_TYPE_D:
        # Order Delete.
        order_ref = int.from_bytes(body[11:19], "big")
        event.update({
            "act": "delete",
            "order_ref": order_ref,
        })

    elif type_byte == MSG_TYPE_U:
        # Order Replace.
        old_ref = int.from_bytes(body[11:19], "big")
        new_ref = int.from_bytes(body[19:27], "big")
        shares = int.from_bytes(body[27:31], "big")
        price = int.from_bytes(body[31:35], "big")
        event.update({
            "act": "replace",
            "order_ref": old_ref,
            "new_ref": new_ref,
            "shares": shares,
            "price": price,
        })

    elif type_byte == MSG_TYPE_R:
        # Stock Directory.  The task table lists stock at [11:18]; the full
        # 39-byte message has additional fields (round lot, lot size, etc.)
        # that are not needed for book reconstruction, so we decode the
        # common subset plus the stock symbol.
        stock = decode_stock(body[11:19])
        event.update({
            "act": "directory",
            "stock": stock,
        })

    else:
        # Unknown / experimental type: emit raw hex for the body.
        event.update({
            "act": "unknown",
            "raw_hex": body.hex(),
        })

    return event


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Golden-reference ITCH 5.0 parser -> JSONL events.",
    )
    parser.add_argument(
        "--input", required=True, help="Raw ITCH 5.0 binary file path."
    )
    parser.add_argument(
        "--output", required=True, help="Output JSONL events file path."
    )
    parser.add_argument(
        "--max", type=int, default=0,
        help="Max messages to decode (0 = all).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.max < 0:
        print("ERROR: --max must be >= 0", file=sys.stderr)
        return 1

    # Per-type counters for the machine-parseable report.
    counts: dict[int, int] = {t: 0 for t in KNOWN_TYPES}
    unknown_count = 0
    total_messages = 0
    total_bytes = 0  # total bytes consumed from the file (prefix + body)

    try:
        with open(args.input, "rb") as fin, open(args.output, "w", encoding="utf-8") as fout:
            while True:
                # Read the 2-byte big-endian length prefix.
                prefix = fin.read(2)
                if not prefix:
                    break  # clean EOF
                if len(prefix) < 2:
                    print(
                        f"ERROR: truncated length prefix at byte {total_bytes} "
                        f"(got {len(prefix)} byte(s))",
                        file=sys.stderr,
                    )
                    return 2

                body_len = struct.unpack(">H", prefix)[0]
                total_bytes += 2 + body_len

                # Read the message body.
                body = fin.read(body_len)
                if len(body) < body_len:
                    print(
                        f"ERROR: truncated message body at byte {total_bytes - body_len} "
                        f"(expected {body_len} bytes, got {len(body)})",
                        file=sys.stderr,
                    )
                    return 2

                # Decode and emit.
                event = parse_message(body)
                fout.write(json.dumps(event, separators=(",", ":")) + "\n")

                type_byte = body[0]
                if type_byte in counts:
                    counts[type_byte] += 1
                else:
                    unknown_count += 1

                total_messages += 1
                if args.max and total_messages >= args.max:
                    break

    except FileNotFoundError:
        print(f"ERROR: input file not readable: {args.input}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"ERROR: I/O error - {e}", file=sys.stderr)
        return 2

    # --- Machine-parseable report -------------------------------------------
    type_summary = ",".join(
        f"{chr(t)}={counts[t]}" for t in sorted(counts)
    )
    if unknown_count:
        type_summary += f",unknown={unknown_count}"
    print(
        f"REF-PARSE: {total_messages} messages decoded "
        f"({type_summary}), {total_bytes} bytes"
    )
    for t in sorted(counts):
        print(f"TYPE-COUNT-{chr(t)}: {counts[t]}")
    if unknown_count:
        print(f"TYPE-COUNT-UNKNOWN: {unknown_count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
