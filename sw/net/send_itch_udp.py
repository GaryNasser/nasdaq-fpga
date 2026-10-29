#!/usr/bin/env python3
"""send_itch_udp.py — replay a project MoldUDP64 file as UDP datagrams.

Each MoldUDP64 packet in the file becomes one UDP datagram containing the
packet byte-for-byte (12-byte header + 2-byte-length-prefixed messages).
This is the traffic source used to exercise `itch_capture.c` (AF_PACKET /
PACKET_MMAP) without a real exchange multicast feed.

    ./send_itch_udp.py --input itch_loc6836.mold64 \
        --host 127.0.0.1 --port 9000 --repeat 3

Use --gap-us to pace the stream; default 0 sends as fast as the socket
allows.  Output is machine-parseable:

    SEND-RESULT: packets=... bytes=... messages=... seconds=... \
                 pkt_per_s=... mbps=...
"""

import argparse
import socket
import sys
import time


def split_packets(data):
    """Yield (packet_bytes, message_count) for the project MoldUDP64 layout."""
    off = 0
    n = len(data)
    while off + 12 <= n:
        start = off
        count = (data[off + 10] << 8) | data[off + 11]
        off += 12
        for _ in range(count):
            if off + 2 > n:
                return
            mlen = (data[off] << 8) | data[off + 1]
            off += 2 + mlen
            if off > n:
                return
        yield data[start:off], count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=9000)
    ap.add_argument('--repeat', type=int, default=1)
    ap.add_argument('--gap-us', type=float, default=0.0,
                    help='sleep between datagrams (microseconds)')
    ap.add_argument('--max-packets', type=int, default=0)
    args = ap.parse_args()

    with open(args.input, 'rb') as f:
        data = f.read()

    pkts = list(split_packets(data))
    if not pkts:
        print('SEND-ERROR: no packets parsed from --input')
        return 2

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Large send buffer: the point is to stress the receive path.
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
    except OSError:
        pass

    total_pkts = 0
    total_bytes = 0
    total_msgs = 0
    t0 = time.perf_counter()
    try:
        for _ in range(args.repeat):
            for pkt, count in pkts:
                sock.sendto(pkt, (args.host, args.port))
                total_pkts += 1
                total_bytes += len(pkt)
                total_msgs += count
                if args.max_packets and total_pkts >= args.max_packets:
                    raise StopIteration
                if args.gap_us > 0:
                    time.sleep(args.gap_us / 1e6)
    except StopIteration:
        pass
    finally:
        t1 = time.perf_counter()
        sock.close()

    dt = t1 - t0
    print(f'SEND-RESULT: packets={total_pkts} bytes={total_bytes} '
          f'messages={total_msgs} seconds={dt:.3f} '
          f'pkt_per_s={total_pkts / dt if dt else 0:.0f} '
          f'mbps={total_bytes * 8 / dt / 1e6 if dt else 0:.1f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
