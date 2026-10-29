#!/usr/bin/env python3
"""Deterministic MoldUDP64 packer for raw ITCH 5.0 binary data.

Reads raw ITCH 5.0 messages and packs them into a MoldUDP64 packet stream.
Each ITCH message is encoded as a 2-byte big-endian length followed by the body.
Messages are greedily accumulated into packets up to a maximum payload size.
"""

import argparse
import struct
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pack raw ITCH 5.0 binary into MoldUDP64 packet stream."
    )
    parser.add_argument(
        "--input", required=True, help="Raw ITCH binary path."
    )
    parser.add_argument(
        "--output", required=True, help="MoldUDP64 output path."
    )
    parser.add_argument(
        "--session", required=True, help="Session name (<=8 chars, right-padded to 8 bytes)."
    )
    parser.add_argument(
        "--seq-start", type=int, default=1, help="Starting sequence number (default: 1)."
    )
    parser.add_argument(
        "--max-payload", type=int, default=1458,
        help="Max bytes of ITCH data per packet (default: 1458).",
    )
    return parser.parse_args()


def pack_itch(input_path: str, output_path: str, session: bytes,
              seq_start: int, max_payload: int) -> tuple[int, int]:
    """Read raw ITCH messages and write MoldUDP64 packets.

    Returns (message_count, packet_count).
    """
    with open(input_path, "rb") as f:
        raw = f.read()

    messages: list[bytes] = []
    offset = 0
    while offset < len(raw):
        if offset + 2 > len(raw):
            raise ValueError(f"Corrupt length prefix at offset {offset}: truncated.")
        msg_len = struct.unpack(">H", raw[offset:offset + 2])[0]
        offset += 2
        if offset + msg_len > len(raw):
            raise ValueError(
                f"Corrupt message at offset {offset - 2}: "
                f"declared length {msg_len} exceeds remaining data."
            )
        messages.append(raw[offset:offset + msg_len])
        offset += msg_len

    packets: list[tuple[int, bytes]] = []
    current_payload = bytearray()
    current_count = 0
    seq = seq_start
    msg_index = 0

    while msg_index < len(messages):
        msg = messages[msg_index]
        msg_len = len(msg)
        needed = 2 + msg_len

        if not current_payload:
            # Start a new packet.
            current_payload.extend(struct.pack(">H", msg_len))
            current_payload.extend(msg)
            current_count += 1
            msg_index += 1
        elif len(current_payload) + needed <= max_payload:
            # Fits in current packet.
            current_payload.extend(struct.pack(">H", msg_len))
            current_payload.extend(msg)
            current_count += 1
            msg_index += 1
        else:
            # Would exceed max_payload; emit current packet.
            packets.append((current_count, bytes(current_payload)))
            current_payload = bytearray()
            current_count = 0

    # Emit the last packet if it has data.
    if current_payload:
        packets.append((current_count, bytes(current_payload)))

    with open(output_path, "wb") as f:
        for count, payload in packets:
            header = struct.pack(">8sHH", session, seq, count)
            f.write(header)
            f.write(payload)
            seq = (seq + 1) & 0xFFFF

    return len(messages), len(packets)


def main() -> int:
    args = parse_args()

    if len(args.session) > 8:
        print(f"ERROR: session must be <=8 chars, got {len(args.session)}", file=sys.stderr)
        return 1

    session_bytes = args.session.encode("ascii").ljust(8, b" ")

    if args.max_payload < 1:
        print("ERROR: --max-payload must be >= 1", file=sys.stderr)
        return 1

    if args.seq_start < 0 or args.seq_start > 0xFFFF:
        print("ERROR: --seq-start must be in range 0..65535", file=sys.stderr)
        return 1

    try:
        msg_count, pkt_count = pack_itch(
            args.input, args.output, session_bytes,
            args.seq_start, args.max_payload,
        )
    except FileNotFoundError:
        print(f"ERROR: input file not readable: {args.input}", file=sys.stderr)
        return 2
    except (ValueError, struct.error) as e:
        print(f"ERROR: parse error - {e}", file=sys.stderr)
        return 3

    print(f"PACK-OK: {msg_count} messages -> {pkt_count} packets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
