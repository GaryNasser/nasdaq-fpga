#!/usr/bin/env python3
"""Fetch and truncate an ITCH 5.0 development subset from Nasdaq public feed.

Streams the gzipped ITCH file, decompresses incrementally, and stops as soon
as the requested number of messages has been decoded.  The full archive is
several GB; streaming avoids ever holding it (compressed or decompressed) in
memory or on disk.

Writes raw ITCH binary (concatenated 2-byte big-endian length-prefixed
messages) plus a JSON sidecar manifest.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timezone


DEFAULT_SOURCE_URL = (
    "https://emi.nasdaq.com/ITCH/Nasdaq%20ITCH/01302019.NASDAQ_ITCH50.gz"
)

# Stop downloading after this many compressed bytes without having reached the
# requested message count: guards against an endless stream of a damaged file.
MAX_COMPRESSED_BYTES = 512 << 20  # 512 MiB


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch ITCH 5.0 subset from Nasdaq public feed.",
    )
    parser.add_argument(
        "--messages", type=int, default=1_000_000,
        help="Target message count (default: 1000000)",
    )
    parser.add_argument(
        "--output", required=True,
        help="Output raw ITCH binary path",
    )
    parser.add_argument(
        "--source-url", default=DEFAULT_SOURCE_URL,
        help="Override download URL",
    )
    return parser.parse_args()


def stream_truncate(response, target: int):
    """Stream-decompress `response`, return (raw_bytes, message_count).

    Stops reading as soon as `target` complete messages have been assembled.
    """
    decomp = zlib.decompressobj(16 + zlib.MAX_WBITS)  # gzip container
    buf = bytearray()
    out = bytearray()
    msgs = 0
    consumed = 0

    while msgs < target:
        chunk = response.read(1 << 16)
        if not chunk:
            break
        consumed += len(chunk)
        try:
            buf.extend(decomp.decompress(chunk))
        except zlib.error as exc:
            raise ConnectionError(f"gzip stream corrupt after {consumed} bytes: {exc}")

        # Walk complete messages out of the decompressed buffer.
        pos = 0
        end = len(buf)
        while msgs < target:
            if end - pos < 2:
                break
            body_len = (buf[pos] << 8) | buf[pos + 1]
            nxt = pos + 2 + body_len
            if nxt > end:
                break
            out.extend(buf[pos:nxt])
            msgs += 1
            pos = nxt
        if pos:
            del buf[:pos]

        if consumed > MAX_COMPRESSED_BYTES:
            raise ConnectionError(
                f"read {consumed} compressed bytes without reaching {target} messages"
            )

    return bytes(out), msgs


def fetch_itch(source_url: str, output_path: str, target_messages: int):
    """Stream the feed, keep the first `target_messages` messages, write them."""
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "nasdaq-fpga-fetcher/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw, count = stream_truncate(response, target_messages)
    except (urllib.error.URLError, OSError) as e:
        raise ConnectionError(f"{source_url} unreachable: {e}") from e

    with open(output_path, "wb") as f:
        f.write(raw)

    manifest = {
        "source_url": source_url,
        "fetch_date": datetime.now(timezone.utc).isoformat(),
        "byte_size": len(raw),
        "message_count": count,
        "truncated": count < target_messages,
        "method": "streaming-gzip/early-abort",
    }
    with open(output_path + ".manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    return count, len(raw)


def main() -> int:
    args = parse_args()

    if args.messages < 1:
        print("ERROR: --messages must be >= 1", file=sys.stderr)
        return 1

    # Idempotent: skip if output already exists.
    if os.path.exists(args.output):
        print(f"FETCH-SKIP: {args.output} exists")
        return 0

    parent = os.path.dirname(args.output)
    if parent:
        os.makedirs(parent, exist_ok=True)

    try:
        message_count, byte_size = fetch_itch(
            args.source_url, args.output, args.messages,
        )
    except ConnectionError as e:
        print(f"FETCH-FAIL: {e}", file=sys.stderr)
        return 2

    print(f"FETCH-OK: {message_count} messages, {byte_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
