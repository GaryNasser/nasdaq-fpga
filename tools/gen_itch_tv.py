#!/usr/bin/env python3
"""gen_itch_tv.py: Verilog-$readmemh-friendly test-vector generator.

Reads a raw ITCH 5.0 binary file and produces self-contained stimuli + expected
output for the RTL testbenches (tb_mold64_reasm, tb_itch_parse).  Packs the raw
ITCH messages into MoldUDP64 packets using the SAME algorithm as
scripts/pack_itch.py so the RTL reassembler sees identical packets.

Outputs (all under --out-dir):
    mold64_stim.txt        — one 64-bit beat per line as 16 hex chars;
                              |TLAST suffix on the last beat of each packet.
    itch_stim_bytes.txt    — raw reassembled ITCH byte stream (golden output
                              of mold64_reasm).  One hex byte per line; blank
                              line between messages (TLAST marker).
    expected_events.jsonl  — golden decoded events (same format as
                              ref_itch_parse.py).
    README.tv              — machine-readable manifest (counts, byte counts).

Usage:
    python tools/gen_itch_tv.py --input <raw_itch> --out-dir <dir> [--n N]
"""

import argparse
import json
import os
import sys

# ---------------------------------------------------------------------------
# Import the MoldUDP64 packer from scripts/pack_itch.py (same directory tree).
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

try:
    from pack_itch import pack_itch  # type: ignore
except ImportError:
    # Fallback: replicate the packer inline if the import fails.
    pack_itch = None  # type: ignore


import struct  # noqa: E402 — after the import attempt above


# ---------------------------------------------------------------------------
# Constants (match mold64_reasm.v defaults)
# ---------------------------------------------------------------------------
DEFAULT_SESSION = "NASDAQ01"
DEFAULT_MAX_PAYLOAD = 1458
BYTES_PER_BEAT = 8  # 64-bit AXI-Stream beat


# ---------------------------------------------------------------------------
# Inline fallback packer (mirrors scripts/pack_itch.py exactly).
# ---------------------------------------------------------------------------
def pack_itch_inline(input_path: str, session: bytes, seq_start: int,
                     max_payload: int) -> tuple[int, int, list[tuple[int, bytes]]]:
    """Read raw ITCH messages and pack into MoldUDP64 packets.

    Returns (message_count, packet_count, packets) where packets is a list of
    (msg_count, full_packet_bytes) tuples.  full_packet_bytes includes the
    12-byte MoldUDP64 header.
    """
    with open(input_path, "rb") as f:
        raw = f.read()

    # Parse raw ITCH messages.
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

    # Greedily accumulate into packets.
    packets: list[tuple[int, bytes]] = []
    current_payload = bytearray()
    current_count = 0
    seq = seq_start

    for msg in messages:
        needed = 2 + len(msg)

        if not current_payload:
            current_payload.extend(struct.pack(">H", len(msg)))
            current_payload.extend(msg)
            current_count += 1
        elif len(current_payload) + needed <= max_payload:
            current_payload.extend(struct.pack(">H", len(msg)))
            current_payload.extend(msg)
            current_count += 1
        else:
            # Emit current packet with header.
            header = struct.pack(">8sHH", session, seq, current_count)
            packets.append((current_count, header + bytes(current_payload)))
            seq = (seq + 1) & 0xFFFF
            current_payload = bytearray()
            current_count = 0
            # Start new packet with this message (oversized messages get their
            # own packet even if they exceed max_payload).
            current_payload.extend(struct.pack(">H", len(msg)))
            current_payload.extend(msg)
            current_count += 1

    if current_payload:
        header = struct.pack(">8sHH", session, seq, current_count)
        packets.append((current_count, header + bytes(current_payload)))

    return len(messages), len(packets), packets


def pack(input_path: str, session: bytes, seq_start: int,
         max_payload: int) -> tuple[int, int, list[tuple[int, bytes]]]:
    """Dispatch to the imported packer or the inline fallback."""
    if pack_itch is not None:
        # Use the real packer: write to a temp file, then re-read packets.
        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix=".mold64")
        os.close(fd)
        try:
            msg_count, pkt_count = pack_itch(
                input_path, tmp_path, session, seq_start, max_payload,
            )
            # Re-read and split into individual packets.
            packets = read_packets_from_file(tmp_path)
            return msg_count, pkt_count, packets
        finally:
            os.remove(tmp_path)
    else:
        return pack_itch_inline(input_path, session, seq_start, max_payload)


def read_packets_from_file(path: str) -> list[tuple[int, bytes]]:
    """Read a packed MoldUDP64 file back into (count, full_packet_bytes)."""
    packets = []
    with open(path, "rb") as f:
        data = f.read()
    pos = 0
    while pos + 12 <= len(data):
        count = struct.unpack(">H", data[pos + 10:pos + 12])[0]
        # Find packet end: walk `count` messages.
        payload_start = pos + 12
        p = payload_start
        for _ in range(count):
            if p + 2 > len(data):
                break
            mlen = struct.unpack(">H", data[p:p + 2])[0]
            p += 2 + mlen
        packets.append((count, data[pos:p]))
        pos = p
    return packets


# ---------------------------------------------------------------------------
# ITCH 5.0 message decoder (shared schema with ref_itch_parse.py)
# ---------------------------------------------------------------------------
MSG_TYPE_A = 0x41
MSG_TYPE_F = 0x46
MSG_TYPE_E = 0x45
MSG_TYPE_C = 0x43
MSG_TYPE_X = 0x58
MSG_TYPE_D = 0x44
MSG_TYPE_U = 0x55
MSG_TYPE_R = 0x52

KNOWN_TYPES = {
    MSG_TYPE_A, MSG_TYPE_F, MSG_TYPE_E, MSG_TYPE_C,
    MSG_TYPE_X, MSG_TYPE_D, MSG_TYPE_U, MSG_TYPE_R,
}


def _decode_timestamp(body: bytes) -> int:
    return int.from_bytes(body[0:6], "big")


def _decode_stock(body: bytes) -> str:
    return body[0:8].decode("ascii", errors="replace").rstrip(" ")


def decode_message(body: bytes) -> dict:
    """Decode one ITCH message body into a JSON event (golden reference)."""
    type_byte = body[0]
    stock_locate = int.from_bytes(body[1:3], "big")
    tracking = int.from_bytes(body[3:5], "big")
    timestamp = _decode_timestamp(body[5:11])

    event = {
        "msg_type": chr(type_byte),
        "stock_locate": stock_locate,
        "tracking": tracking,
        "timestamp": timestamp,
    }

    if type_byte in (MSG_TYPE_A, MSG_TYPE_F):
        order_ref = int.from_bytes(body[11:19], "big")
        side = chr(body[19])
        shares = int.from_bytes(body[20:24], "big")
        stock = _decode_stock(body[24:32])
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
            event["mpid"] = body[32:36].decode("ascii", errors="replace").rstrip(" ")
            event["price"] = int.from_bytes(body[36:40], "big")

    elif type_byte in (MSG_TYPE_E, MSG_TYPE_C):
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
            event["price"] = int.from_bytes(body[27:31], "big")

    elif type_byte == MSG_TYPE_X:
        order_ref = int.from_bytes(body[11:19], "big")
        shares = int.from_bytes(body[19:23], "big")
        event.update({
            "act": "cancel",
            "order_ref": order_ref,
            "shares": shares,
        })

    elif type_byte == MSG_TYPE_D:
        order_ref = int.from_bytes(body[11:19], "big")
        event.update({
            "act": "delete",
            "order_ref": order_ref,
        })

    elif type_byte == MSG_TYPE_U:
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
        stock = _decode_stock(body[11:19])
        event.update({
            "act": "directory",
            "stock": stock,
        })

    else:
        event.update({
            "act": "unknown",
            "raw_hex": body.hex(),
        })

    return event


# ---------------------------------------------------------------------------
# Stimulus generation helpers
# ---------------------------------------------------------------------------
def read_raw_messages(path: str) -> list[bytes]:
    """Read raw ITCH messages as a list of body bytes (no length prefix)."""
    with open(path, "rb") as f:
        raw = f.read()
    messages = []
    offset = 0
    while offset + 2 <= len(raw):
        msg_len = struct.unpack(">H", raw[offset:offset + 2])[0]
        offset += 2
        if offset + msg_len > len(raw):
            raise ValueError(f"Truncated message at offset {offset - 2}")
        messages.append(raw[offset:offset + msg_len])
        offset += msg_len
    return messages


def packets_to_stim_bytes(packets: list[tuple[int, bytes]]) -> list[bytes]:
    """Flatten packets into a single byte stream (header + payload each)."""
    out = bytearray()
    for _, pkt in packets:
        out.extend(pkt)
    return bytes(out)


def bytes_to_beat_lines(data: bytes) -> list[tuple[str, bool]]:
    """Convert a byte stream into 64-bit beat lines for mold64_stim.txt.

    Returns list of (hex_line, is_tlast_beat).  Each line is 16 hex chars
    (8 bytes).  The final beat may be partial (< 8 bytes); we still emit
    16 hex chars but the testbench is expected to drive only the valid
    bytes (the |TLAST comment marks it).  Zero-pad incomplete trailing beats.
    """
    lines = []
    for i in range(0, len(data), BYTES_PER_BEAT):
        chunk = data[i:i + BYTES_PER_BEAT]
        is_last = (i + BYTES_PER_BEAT) >= len(data)
        # Pad to 8 bytes if partial (zero-fill; testbench drives via tkeep).
        if len(chunk) < BYTES_PER_BEAT:
            chunk = chunk + b"\x00" * (BYTES_PER_BEAT - len(chunk))
        lines.append((chunk.hex().upper(), is_last))
    return lines


def reassemble_messages(packets: list[tuple[int, bytes]]) -> list[bytes]:
    """Walk MoldUDP64 packets and extract the reassembled ITCH byte stream.

    Returns a list of ITCH message bodies (with their 2-byte length prefix
    intact, matching what mold64_reasm's M_AXIS emits byte-by-byte).
    """
    messages = []
    for _, pkt in packets:
        pos = 12  # skip 8-byte session + 2 seq + 2 count
        while pos + 2 <= len(pkt):
            mlen = struct.unpack(">H", pkt[pos:pos + 2])[0]
            if pos + 2 + mlen > len(pkt):
                break  # truncated within packet
            messages.append(pkt[pos:pos + 2 + mlen])  # include length prefix
            pos += 2 + mlen
    return messages


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Verilog $readmemh ITCH test vectors.",
    )
    parser.add_argument(
        "--input", required=True, help="Raw ITCH 5.0 binary file path.",
    )
    parser.add_argument(
        "--out-dir", required=True, help="Output directory for test vectors.",
    )
    parser.add_argument(
        "--n", type=int, default=0,
        help="Limit to first N messages (0 = all).",
    )
    parser.add_argument(
        "--session", default=DEFAULT_SESSION,
        help=f"MOLDUDP64 session name (default: {DEFAULT_SESSION}).",
    )
    parser.add_argument(
        "--max-payload", type=int, default=DEFAULT_MAX_PAYLOAD,
        help=f"Max payload bytes per packet (default: {DEFAULT_MAX_PAYLOAD}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not os.path.isfile(args.input):
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        return 2

    if args.max_payload < 1:
        print("ERROR: --max-payload must be >= 1", file=sys.stderr)
        return 1

    if len(args.session) > 8:
        print(f"ERROR: session must be <=8 chars, got {len(args.session)}",
              file=sys.stderr)
        return 1

    session_bytes = args.session.encode("ascii").ljust(8, b" ")

    # Ensure output directory exists.
    os.makedirs(args.out_dir, exist_ok=True)

    # --- Step 1: read raw ITCH messages (optionally truncate) --------------
    try:
        messages = read_raw_messages(args.input)
    except (ValueError, OSError) as e:
        print(f"ERROR: failed to read raw ITCH - {e}", file=sys.stderr)
        return 2

    if args.n > 0:
        messages = messages[: args.n]

    # Write a temp file with just the selected messages so the packer
    # sees exactly what we want to encode.
    import tempfile
    fd, tmp_raw = tempfile.mkstemp(suffix=".itch")
    os.close(fd)
    try:
        with open(tmp_raw, "wb") as f:
            for msg in messages:
                f.write(struct.pack(">H", len(msg)))
                f.write(msg)

        # --- Step 2: pack into MoldUDP64 packets ---------------------------
        msg_count, pkt_count, packets = pack(
            tmp_raw, session_bytes, 1, args.max_payload,
        )
    finally:
        os.remove(tmp_raw)

    # --- Step 3: write mold64_stim.txt ------------------------------------
    stim_path = os.path.join(args.out_dir, "mold64_stim.txt")
    stim_bytes_total = 0
    with open(stim_path, "w", encoding="utf-8") as f:
        f.write("// MoldUDP64 packet stimuli — one 64-bit beat per line\n")
        f.write("// 16 hex chars = 8 bytes (64 bits), |TLAST marks packet end\n")
        f.write("// session={} seq_start=1 max_payload={}\n".format(
            args.session, args.max_payload,
        ))
        seq = 1
        for msg_count_pkt, pkt in packets:
            f.write("// session={} seq={} count={}\n".format(
                args.session, seq, msg_count_pkt,
            ))
            seq = (seq + 1) & 0xFFFF
            beat_lines = bytes_to_beat_lines(pkt)
            for hex_line, is_tlast in beat_lines:
                suffix = " |TLAST" if is_tlast else ""
                f.write(f"{hex_line}{suffix}\n")
                stim_bytes_total += 8  # logical beat width (including padding)

    # --- Step 4: write itch_stim_bytes.txt --------------------------------
    bytes_path = os.path.join(args.out_dir, "itch_stim_bytes.txt")
    reassembled = reassemble_messages(packets)
    raw_itch_byte_count = 0
    with open(bytes_path, "w", encoding="utf-8") as f:
        f.write("// Reassembled ITCH byte stream (golden mold64_reasm output)\n")
        f.write("// One hex byte per line; blank line = TLAST between messages\n")
        for msg_bytes in reassembled:
            for b in msg_bytes:
                f.write(f"{b:02X}\n")
                raw_itch_byte_count += 1
            f.write("\n")  # blank line = message boundary (TLAST)

    # --- Step 5: write expected_events.jsonl ------------------------------
    events_path = os.path.join(args.out_dir, "expected_events.jsonl")
    type_counts: dict[str, int] = {}
    with open(events_path, "w", encoding="utf-8") as f:
        for msg_bytes in reassembled:
            body = msg_bytes[2:]  # strip 2-byte length prefix
            event = decode_message(body)
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
            key = event["msg_type"]
            type_counts[key] = type_counts.get(key, 0) + 1

    # --- Step 6: write README.tv manifest ---------------------------------
    readme_path = os.path.join(args.out_dir, "README.tv")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(f"source_file: {os.path.abspath(args.input)}\n")
        f.write(f"session: {args.session}\n")
        f.write(f"seq_start: 1\n")
        f.write(f"max_payload: {args.max_payload}\n")
        f.write(f"message_count: {msg_count}\n")
        f.write(f"packet_count: {pkt_count}\n")
        f.write(f"raw_itch_bytes: {raw_itch_byte_count}\n")
        f.write(f"stim_beat_bytes: {stim_bytes_total}\n")
        f.write("type_counts:\n")
        for t in sorted(type_counts):
            f.write(f"  {t}: {type_counts[t]}\n")

    # --- Result line -------------------------------------------------------
    def _safe_type_char(t: str) -> str:
        """Return ASCII-safe type-char representation (escape non-printable)."""
        if len(t) == 1 and (ord(t) < 0x20 or ord(t) > 0x7E):
            return f"\\\\x{ord(t):02X}"
        return t

    type_summary = ",".join(
        f"{_safe_type_char(t)}={type_counts[t]}" for t in sorted(type_counts)
    )
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    print(
        f"GEN-TV: {msg_count} messages -> {pkt_count} packets "
        f"({type_summary}), dir={args.out_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
