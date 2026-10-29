/*
 * send_itch_udp.c — C traffic source for the M6 PACKET_MMAP capture test.
 *
 * Replays a project MoldUDP64 file as UDP datagrams (one datagram per
 * packet, byte-for-byte).  A bound-but-never-read sink socket keeps the
 * kernel from emitting ICMP port-unreachable replies, which would otherwise
 * pollute the capture.
 *
 * Build (on the board):
 *   gcc -O3 -march=armv7-a -mfpu=neon -mfloat-abi=hard -o send_itch_udp \
 *       send_itch_udp.c
 * Run:
 *   ./send_itch_udp --input itch_loc6836.mold64 --port 9000 --repeat 10
 */

#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <inttypes.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define MAX_PKTS 262144

static double now_s(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static int load_packets(const uint8_t *data, size_t len,
                        const uint8_t **pkts, size_t *lens, unsigned *msgs)
{
    size_t off = 0;
    int n = 0;

    while (off + 12 <= len && n < MAX_PKTS) {
        size_t start = off;
        unsigned count = ((unsigned)data[off + 10] << 8) | data[off + 11];
        unsigned i;

        off += 12;
        for (i = 0; i < count; i++) {
            unsigned mlen;
            if (off + 2 > len) return n;
            mlen = ((unsigned)data[off] << 8) | data[off + 1];
            off += 2 + mlen;
            if (off > len) return n;
        }
        pkts[n] = data + start;
        lens[n] = off - start;
        msgs[n] = count;
        n++;
    }
    return n;
}

int main(int argc, char **argv)
{
    const char *input = NULL;
    const char *host = "127.0.0.1";
    unsigned port = 9000;
    unsigned repeat = 1;
    double gap_us = 0.0;
    int i;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--input") && i + 1 < argc) input = argv[++i];
        else if (!strcmp(argv[i], "--host") && i + 1 < argc) host = argv[++i];
        else if (!strcmp(argv[i], "--port") && i + 1 < argc)
            port = (unsigned)strtoul(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--repeat") && i + 1 < argc)
            repeat = (unsigned)strtoul(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--gap-us") && i + 1 < argc)
            gap_us = strtod(argv[++i], NULL);
        else {
            fprintf(stderr, "unknown argument: %s\n", argv[i]);
            return 1;
        }
    }
    if (!input) {
        fprintf(stderr, "usage: %s --input <file> [--host H] [--port P] "
                        "[--repeat N] [--gap-us U]\n", argv[0]);
        return 1;
    }

    /* Read the file. */
    FILE *f = fopen(input, "rb");
    if (!f) { fprintf(stderr, "open %s: %s\n", input, strerror(errno)); return 2; }
    fseek(f, 0, SEEK_END);
    long flen = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *data = malloc((size_t)flen);
    if (!data || fread(data, 1, (size_t)flen, f) != (size_t)flen) {
        fprintf(stderr, "read %s failed\n", input);
        return 2;
    }
    fclose(f);

    static const uint8_t *pkts[MAX_PKTS];
    static size_t lens[MAX_PKTS];
    static unsigned msgs[MAX_PKTS];
    int npkts = load_packets(data, (size_t)flen, pkts, lens, msgs);
    if (npkts <= 0) { fprintf(stderr, "no packets in %s\n", input); return 2; }

    /* Sink socket: keeps ICMP port-unreachable out of the capture. */
    int sink = socket(AF_INET, SOCK_DGRAM, 0);
    if (sink >= 0) {
        int rcvbuf = 1 << 20;
        struct sockaddr_in sa;
        setsockopt(sink, SOL_SOCKET, SO_RCVBUF, &rcvbuf, sizeof(rcvbuf));
        memset(&sa, 0, sizeof(sa));
        sa.sin_family = AF_INET;
        sa.sin_addr.s_addr = htonl(INADDR_ANY);
        sa.sin_port = htons((uint16_t)port);
        bind(sink, (struct sockaddr *)&sa, sizeof(sa));
    }

    int s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0) { fprintf(stderr, "socket: %s\n", strerror(errno)); return 2; }
    {
        int sndbuf = 4 << 20;
        setsockopt(s, SOL_SOCKET, SO_SNDBUF, &sndbuf, sizeof(sndbuf));
    }

    struct sockaddr_in dst;
    memset(&dst, 0, sizeof(dst));
    dst.sin_family = AF_INET;
    dst.sin_port = htons((uint16_t)port);
    if (inet_pton(AF_INET, host, &dst.sin_addr) != 1) {
        fprintf(stderr, "bad host %s\n", host);
        return 2;
    }

    uint64_t total_pkts = 0, total_bytes = 0, total_msgs = 0;
    double t0 = now_s();
    for (unsigned r = 0; r < repeat; r++) {
        for (int p = 0; p < npkts; p++) {
            ssize_t rc = sendto(s, pkts[p], lens[p], 0,
                                (struct sockaddr *)&dst, sizeof(dst));
            if (rc < 0) continue;   /* ENOBUFS / EAGAIN: sender-side overflow */
            total_pkts++;
            total_bytes += (uint64_t)rc;
            total_msgs += msgs[p];
            if (gap_us > 0) usleep((useconds_t)gap_us);
        }
    }
    double dt = now_s() - t0;

    printf("SEND-RESULT: packets=%" PRIu64 " bytes=%" PRIu64
           " messages=%" PRIu64 " seconds=%.3f pkt_per_s=%.0f mbps=%.1f\n",
           total_pkts, total_bytes, total_msgs, dt,
           dt > 0 ? (double)total_pkts / dt : 0.0,
           dt > 0 ? (double)total_bytes * 8.0 / dt / 1e6 : 0.0);
    close(s);
    if (sink >= 0) close(sink);
    return 0;
}
