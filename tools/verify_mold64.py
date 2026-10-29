#!/usr/bin/env python3
"""verify_mold64.py: reference MoldUDP64 parser for round-trip verification.

Reads a packed MoldUDP64 file and a raw ITCH reference, confirms every
original message is recovered in order with no loss or duplication.
"""

import argparse
import struct
import sys


def read_raw_itch_messages(path):
    """Read raw ITCH 5.0 messages (2-byte BE length + body)."""
    messages = []
    with open(path, "rb") as f:
        data = f.read()
    pos = 0
    while pos < len(data):
        if pos + 2 > len(data):
            raise ValueError(f"Truncated length prefix at byte {pos}")
        length = struct.unpack(">H", data[pos : pos + 2])[0]
        if pos + 2 + length > len(data):
            raise ValueError(f"Truncated message body at byte {pos} (len={length})")
        messages.append(data[pos + 2 : pos + 2 + length])
        pos += 2 + length
    return messages


def read_mold64_messages(path):
    """Read MoldUDP64 packet stream and extract all ITCH messages."""
    messages = []
    with open(path, "rb") as f:
        data = f.read()
    pos = 0
    while pos < len(data):
        # Packet header: 8-byte session + 2-byte BE sequence + 2-byte BE count
        if pos + 12 > len(data):
            raise ValueError(f"Truncated MoldUDP64 header at byte {pos}")
        count = struct.unpack(">H", data[pos + 10 : pos + 12])[0]
        pos += 12
        for _ in range(count):
            if pos + 2 > len(data):
                raise ValueError(f"Truncated message length at byte {pos}")
            length = struct.unpack(">H", data[pos : pos + 2])[0]
            if pos + 2 + length > len(data):
                raise ValueError(f"Truncated message body at byte {pos}")
            messages.append(data[pos + 2 : pos + 2 + length])
            pos += 2 + length
    return messages


def main():
    parser = argparse.ArgumentParser(description="Verify MoldUDP64 packer round-trip")
    parser.add_argument("--input", required=True, help="Raw ITCH reference file")
    parser.add_argument("--packed", required=True, help="Packed MoldUDP64 file")
    args = parser.parse_args()

    try:
        original = read_raw_itch_messages(args.input)
        recovered = read_mold64_messages(args.packed)
    except ValueError as e:
        print(f"VERIFY-FAIL: parse error — {e}", file=sys.stderr)
        sys.exit(3)

    lost = len(original) - len(recovered) if len(original) > len(recovered) else 0
    duplicated = len(recovered) - len(original) if len(recovered) > len(original) else 0

    if lost == 0 and duplicated == 0 and original == recovered:
        print(f"ROUNDTRIP-OK: {len(recovered)} messages recovered, 0 lost, 0 duplicated")
        sys.exit(0)
    else:
        # Find first mismatch for detail
        mismatch_pos = -1
        for i in range(min(len(original), len(recovered))):
            if original[i] != recovered[i]:
                mismatch_pos = i
                break
        detail = f"first mismatch at message {mismatch_pos}" if mismatch_pos >= 0 else ""
        print(
            f"ROUNDTRIP-FAIL: {len(recovered)}/{len(original)} messages, "
            f"{lost} lost, {duplicated} duplicated. {detail}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
