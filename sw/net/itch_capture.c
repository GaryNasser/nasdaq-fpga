/*
 * itch_capture.c — M6 capture path: PACKET_MMAP (TPACKET_V2) UDP receiver.
 *
 * This is the PS-side entry point of the planned network mode (replan
 * "模式 B").  It opens an AF_PACKET socket with a memory-mapped RX ring,
 * filters UDP datagrams by port, and validates the project MoldUDP64
 * framing (8-byte session "NASDAQ01" + 2-byte sequence + 2-byte count +
 * 2-byte-length-prefixed ITCH messages).
 *
 * Why this exists: the PYNQ-Z2 has no PL-side Ethernet, so packets must be
 * received by the PS.  PACKET_MMAP is the lowest-overhead Linux path
 * (zero-copy ring, one mmap instead of one recvfrom per packet).  This
 * program measures that path and reports kernel/ring drops, which is the
 * evidence needed before wiring the ring into the PL pipeline.
 *
 * IMPORTANT SCOPE: this tool does NOT feed the PL.  Its numbers are the
 * PS capture ceiling, not the PL "K1 line-rate, 0 drops" claim.  See
 * docs/final-report.md §8.
 *
 * Build (on the board):
 *   gcc -O3 -march=armv7-a -o itch_capture itch_capture.c
 * Run (root — AF_PACKET needs CAP_NET_RAW):
 *   sudo ./itch_capture --iface lo --port 9000 --seconds 5
 *
 * Output:
 *   CAPTURE-RESULT: frames=... bytes=... packets=... messages=... drops=...
 *                   seconds=... frames_per_s=... mbps=...
 *   CAPTURE-OK / CAPTURE-ERROR: ...
 */

#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <inttypes.h>
#include <linux/if_ether.h>
#include <linux/if_packet.h>
#include <net/if.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define BLOCK_SIZE  (1u << 18)      /* 256 KiB per ring block */
#define BLOCK_NR    16              /* 4 MiB ring: fits the board's RAM */
#define FRAME_SIZE  2048
#define SESSION     0x4E41534441513031ULL  /* "NASDAQ01" */

static double now_s(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

/* Walk one MoldUDP64 packet payload; returns message count, or -1 if the
 * framing is inconsistent.  Also validates the session bytes. */
static int scan_mold64(const uint8_t *p, unsigned len, int *session_ok)
{
    unsigned off = 0;
    unsigned count;
    int n = 0;

    if (len < 12) return -1;
    {
        uint64_t sess = 0;
        int i;
        for (i = 0; i < 8; i++) sess = (sess << 8) | p[i];
        *session_ok = (sess == SESSION);
    }
    count = ((unsigned)p[10] << 8) | p[11];
    off = 12;
    while (off + 2 <= len) {
        unsigned mlen = ((unsigned)p[off] << 8) | p[off + 1];
        off += 2;
        if (mlen == 0 || off + mlen > len) return -1;
        off += mlen;
        n++;
    }
    return (n == (int)count) ? n : -1;
}

int main(int argc, char **argv)
{
    const char *iface = "eth0";
    unsigned port = 0;
    double seconds = 5.0;
    int i;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--iface") && i + 1 < argc) {
            iface = argv[++i];
        } else if (!strcmp(argv[i], "--port") && i + 1 < argc) {
            port = (unsigned)strtoul(argv[++i], NULL, 10);
        } else if (!strcmp(argv[i], "--seconds") && i + 1 < argc) {
            seconds = strtod(argv[++i], NULL);
        } else {
            fprintf(stderr, "unknown argument: %s\n", argv[i]);
            return 1;
        }
    }

    /* ---- socket + ring setup ------------------------------------------- */
    int fd = socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL));
    if (fd < 0) {
        fprintf(stderr, "socket(AF_PACKET): %s (run as root)\n", strerror(errno));
        return 2;
    }

    struct ifreq ifr;
    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, iface, IFNAMSIZ - 1);
    if (ioctl(fd, SIOCGIFINDEX, &ifr) < 0) {
        fprintf(stderr, "SIOCGIFINDEX(%s): %s\n", iface, strerror(errno));
        return 2;
    }

    int ver = TPACKET_V2;
    if (setsockopt(fd, SOL_PACKET, PACKET_VERSION, &ver, sizeof(ver)) < 0) {
        fprintf(stderr, "PACKET_VERSION: %s\n", strerror(errno));
        return 2;
    }

    struct tpacket_req req;
    memset(&req, 0, sizeof(req));
    req.tp_block_size = BLOCK_SIZE;
    req.tp_block_nr   = BLOCK_NR;
    req.tp_frame_size = FRAME_SIZE;
    req.tp_frame_nr   = (BLOCK_SIZE / FRAME_SIZE) * BLOCK_NR;
    if (setsockopt(fd, SOL_PACKET, PACKET_RX_RING, &req, sizeof(req)) < 0) {
        fprintf(stderr, "PACKET_RX_RING: %s\n", strerror(errno));
        return 2;
    }

    size_t ring_len = (size_t)BLOCK_SIZE * BLOCK_NR;
    uint8_t *ring = mmap(NULL, ring_len, PROT_READ | PROT_WRITE,
                         MAP_SHARED, fd, 0);
    if (ring == MAP_FAILED) {
        fprintf(stderr, "mmap: %s\n", strerror(errno));
        return 2;
    }

    struct sockaddr_ll sll;
    memset(&sll, 0, sizeof(sll));
    sll.sll_family   = AF_PACKET;
    sll.sll_protocol = htons(ETH_P_ALL);
    sll.sll_ifindex  = ifr.ifr_ifindex;
    if (bind(fd, (struct sockaddr *)&sll, sizeof(sll)) < 0) {
        fprintf(stderr, "bind: %s\n", strerror(errno));
        return 2;
    }
#ifdef PACKET_IGNORE_OUTGOING
    {
        int one = 1;
        /* Count only the receive-side tap; otherwise loopback/UDP tests see
         * every datagram twice (xmit tap + rx tap). */
        setsockopt(fd, SOL_PACKET, PACKET_IGNORE_OUTGOING, &one, sizeof(one));
    }
#endif

    /* ---- drain loop -----------------------------------------------------
     * TPACKET_V2 fills blocks in order and marks each frame TP_STATUS_USER
     * as it is queued.  The reader must consume the current block to the
     * end before moving on: a block is only complete when all of its
     * frames have been seen, and the kernel does not start the next block
     * until then.  (Advancing on the first frame, as a naive loop does,
     * abandons the rest of the block and loses most frames.) */
    uint64_t frames = 0, bytes = 0, packets = 0, messages = 0;
    uint64_t framing_bad = 0, blocks = 0, polls = 0;
    unsigned cur_block = 0, cur_off = 0;

    double t0 = now_s();
    while (now_s() - t0 < seconds) {
        uint8_t *base = ring + (size_t)cur_block * BLOCK_SIZE;
        int progressed = 0;

        while (cur_off + FRAME_SIZE <= BLOCK_SIZE) {
            struct tpacket_hdr *fh = (struct tpacket_hdr *)(base + cur_off);
            unsigned flen = fh->tp_len;

            __sync_synchronize();
            if (!(fh->tp_status & TP_STATUS_USER)) break;
            if (flen == 0 || cur_off + fh->tp_snaplen > BLOCK_SIZE) break;

            frames++;
            bytes += flen;

            /* Parse link-layer → IPv4 → UDP, if we can.  Loopback and
             * Ethernet differ in the link header, but tp_net gives the
             * network-header offset directly.  Fall back to the 14-byte
             * Ethernet header if tp_net was not populated. */
            {
                unsigned net_off = fh->tp_net;
                if ((net_off == 0 || net_off + 20 > fh->tp_snaplen) &&
                    fh->tp_snaplen > 14) {
                    net_off = 14;
                }
                if (net_off + 20 <= fh->tp_snaplen &&
                    (base[cur_off + net_off] >> 4) == 4) {
                    const uint8_t *ip = base + cur_off + net_off;
                    unsigned ihl = (unsigned)(ip[0] & 0x0f) * 4u;
                    if (ip[9] == 17 && net_off + ihl + 8 <= fh->tp_snaplen) {
                        const uint8_t *udp = ip + ihl;
                        unsigned dport = ((unsigned)udp[2] << 8) | udp[3];
                        unsigned ulen  = ((unsigned)udp[4] << 8) | udp[5];
                        const uint8_t *pl = udp + 8;
                        unsigned plen = ulen >= 8 ? ulen - 8 : 0;
                        if (port == 0 || dport == port) {
                            int sess_ok = 0;
                            int n = scan_mold64(pl, plen, &sess_ok);
                            if (n >= 0 && sess_ok) {
                                packets++;
                                messages += (unsigned)n;
                            } else {
                                framing_bad++;
                            }
                        }
                    }
                }
            }

            fh->tp_status = TP_STATUS_KERNEL;
            __sync_synchronize();
            cur_off += FRAME_SIZE;
            progressed = 1;
        }

        if (cur_off + FRAME_SIZE > BLOCK_SIZE) {
            /* Block fully consumed: hand it back and move to the next. */
            cur_block = (cur_block + 1) % BLOCK_NR;
            cur_off = 0;
            blocks++;
        } else if (!progressed) {
            struct pollfd pfd = { .fd = fd, .events = POLLIN };
            if (poll(&pfd, 1, 50) > 0) polls++;
        }
    }

    double elapsed = now_s() - t0;

    /* ---- kernel statistics (drops seen by the ring) --------------------- */
    struct tpacket_stats st;
    socklen_t slen = sizeof(st);
    memset(&st, 0, sizeof(st));
    if (getsockopt(fd, SOL_PACKET, PACKET_STATISTICS, &st, &slen) < 0) {
        fprintf(stderr, "PACKET_STATISTICS: %s\n", strerror(errno));
    }

    printf("CAPTURE-RESULT: frames=%" PRIu64 " bytes=%" PRIu64
           " packets=%" PRIu64 " messages=%" PRIu64
           " framing_bad=%" PRIu64 " blocks=%" PRIu64 " polls=%" PRIu64
           " drops=%u seconds=%.3f frames_per_s=%.0f mbps=%.1f\n",
           frames, bytes, packets, messages, framing_bad, blocks, polls,
           st.tp_drops,
           elapsed,
           elapsed > 0 ? (double)frames / elapsed : 0.0,
           elapsed > 0 ? (double)bytes * 8.0 / elapsed / 1e6 : 0.0);

    if (st.tp_drops != 0) {
        printf("CAPTURE-ERROR: %u ring drops\n", st.tp_drops);
        return 3;
    }
    if (packets == 0) {
        printf("CAPTURE-ERROR: no MoldUDP64 packets matched\n");
        return 4;
    }
    if (framing_bad != 0) {
        printf("CAPTURE-ERROR: %" PRIu64 " malformed packets\n", framing_bad);
        return 4;
    }
    printf("CAPTURE-OK: 0 ring drops\n");
    return 0;
}
