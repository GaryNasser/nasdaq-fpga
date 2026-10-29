/*
 * itch_book_baseline.c — A9 software baseline for the PL ITCH pipeline.
 *
 * This program mirrors the *exact* semantics of the RTL order book
 * (rtl/itch/order_book.v) so that the measured throughput is an
 * apples-to-apples comparison with the FPGA implementation:
 *
 *   order_map : direct-mapped, index = order_ref[11:0], tag = order_ref[63:12]
 *   level_table: linear array of 256 entries, matched by PRICE ONLY (the RTL
 *                level entry carries no side bit), all 256 indices usable (0..255;
 *                round 7 fixed an off-by-one that refused index 255), linear search
 *                from index 0 on every ADD
 *   ADD       : duplicate order_ref -> drop.  Otherwise reuse a level with the
 *               same price (shares +=, count += 1), else allocate the next
 *               free level.  Then write order_map and bump order_cnt.
 *   EXECUTE   : map hit required; level shares -= shares.  If the level is
 *   CANCEL      depleted (level.shares <= event shares) the level is
 *               invalidated; otherwise it keeps its reduced size.  The order
 *               is removed from order_map entirely (the RTL does not track
 *               partial fills per order).
 *   DELETE    : map hit required; order_map entry invalidated, order_cnt -= 1.
 *               Level shares are NOT reduced (matches the RTL).
 *   REPLACE   : map hit required; the old order_map entry is invalidated and
 *               the new order is NOT inserted (matches the RTL: ST_LEV_UPDATE
 *               has no ACT_REPLACE arm, so the event terminates in IDLE).
 *   DIRECTORY : no book effect.
 *
 * Input format (same as the PL data path):
 *   default  : MoldUDP64 file — per packet:
 *              session[8] + seq[2] + count[2] + count x {len[2] + body[len]}
 *   --raw    : bare ITCH stream — sequence of {len[2] + body[len]}
 *
 * Output: a machine-parseable summary line plus JSON so the numbers can be
 * diffed against the PL counters (BOOK_ADD_CNT ... BOOK_DROP_CNT).
 *
 * Build (on the board):
 *   gcc -O3 -march=armv7-a -mfpu=neon -mfloat-abi=hard -o itch_book_baseline \
 *       itch_book_baseline.c
 * Run:
 *   ./itch_book_baseline --input data/itch_dev.mold64
 */

#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#endif

#define ORDERS        4096
#define LEVELS        256
#define ORD_ADDR_W    12
#define LEVEL_ADDR_W  8
#define ORD_MASK      ((1u << ORD_ADDR_W) - 1u)
#define LEVEL_MASK    ((1u << LEVEL_ADDR_W) - 1u)

/* ----------------------------------------------------------------------- */
/* Book data structures (semantics mirror the RTL, layout does not)         */
/* ----------------------------------------------------------------------- */

typedef struct {
    uint64_t tag;      /* order_ref[63:12] */
    uint16_t level;    /* level index      */
    uint8_t  valid;
} map_entry_t;

typedef struct {
    uint32_t price;
    uint32_t shares;
    uint16_t count;
    uint8_t  valid;
} level_t;

typedef struct {
    map_entry_t map[ORDERS];
    level_t     lev[LEVELS];
    uint16_t    next_free_level;

    uint32_t order_cnt;
    uint32_t level_cnt;
    uint32_t add_cnt, exe_cnt, can_cnt, del_cnt, rep_cnt, drop_cnt;

    /* BBO — updated exactly like ST_BBO, including the price-only level
     * sharing quirk of the RTL. */
    uint32_t bid_price, bid_shares; uint16_t bid_level; uint8_t bid_valid;
    uint32_t ask_price, ask_shares; uint16_t ask_level; uint8_t ask_valid;
} book_t;

static void book_init(book_t *b)
{
    memset(b, 0, sizeof(*b));
    b->next_free_level = 0;
}

/* Allocate a level for a price.  Returns the level index, or -1 when the
 * table is full (allocator refuses to use index LEVELS-1). */
static int level_alloc(book_t *b, uint32_t price, uint32_t shares,
                       int search_found, int found_level)
{
    if (search_found) {
        b->lev[found_level].shares += shares;
        b->lev[found_level].count  += 1;
        return found_level;
    }
    /* Round 19: the RTL's full test is `level_cnt >= LEVELS`, not `next_free_level >= LEVELS - 1`.
       next_free_level is LEVEL_ADDR_W bits wide and cannot represent LEVELS, so the old form
       made index 255 unreachable. Mirrors rtl/itch/order_book.v after round 7. */
if (b->level_cnt >= LEVELS)
        return -1;
    {
        int idx = b->next_free_level;
        b->lev[idx].price  = price;
        b->lev[idx].shares = shares;
        b->lev[idx].count  = 1;
        b->lev[idx].valid  = 1;
        b->next_free_level++;
        b->level_cnt++;
        return idx;
    }
}

/* ADD path: duplicate check, linear level search, insert. */
static void do_add(book_t *b, uint64_t ref, int side, uint32_t shares,
                   uint32_t price)
{
    unsigned idx = (unsigned)(ref & ORD_MASK);
    uint64_t tag = ref >> ORD_ADDR_W;
    int found = -1;
    int i;

    b->add_cnt++;

    if (b->map[idx].valid && b->map[idx].tag == tag) {
        b->drop_cnt++;
        return;
    }

    /* Linear search from level 0 for a valid level at this price. */
    for (i = 0; i < LEVELS; i++) {   /* round 19: search must reach index 255 */
        if (b->lev[i].valid && b->lev[i].price == price) {
            found = i;
            break;
        }
    }

    {
        int lv = level_alloc(b, price, shares, found >= 0, found);
        if (lv < 0) {
            b->drop_cnt++;
            return;
        }
        b->map[idx].tag   = tag;
        b->map[idx].level = (uint16_t)lv;
        b->map[idx].valid = 1;
        b->order_cnt++;
    }

    /* ST_BBO for ADD. */
    if (!side) {
        if (!b->bid_valid || price > b->bid_price) {
            b->bid_valid = 1; b->bid_price = price;
            b->bid_shares = shares;
            b->bid_level = b->map[idx].level;
        } else if (price == b->bid_price) {
            b->bid_shares += shares;
        }
    } else {
        if (!b->ask_valid || price < b->ask_price) {
            b->ask_valid = 1; b->ask_price = price;
            b->ask_shares = shares;
            b->ask_level = b->map[idx].level;
        } else if (price == b->ask_price) {
            b->ask_shares += shares;
        }
    }
}

/* EXECUTE / CANCEL path. */
static void do_reduce(book_t *b, uint64_t ref, int side, uint32_t shares,
                      int is_exec)
{
    unsigned idx = (unsigned)(ref & ORD_MASK);
    uint64_t tag = ref >> ORD_ADDR_W;
    uint16_t lv;
    uint32_t lev_shares;

    if (is_exec) b->exe_cnt++; else b->can_cnt++;

    if (!b->map[idx].valid || b->map[idx].tag != tag) {
        b->drop_cnt++;
        return;
    }

    lv = b->map[idx].level;
    lev_shares = b->lev[lv].shares;

    if (lev_shares > shares) {
        b->lev[lv].shares = lev_shares - shares;
    } else {
        b->lev[lv].shares = 0;
        b->lev[lv].count  = 0;
        b->lev[lv].valid  = 0;
        if (b->level_cnt > 0) b->level_cnt--;
    }

    /* The RTL removes the order from order_map after any execution/cancel. */
    b->map[idx].valid = 0;
    if (b->order_cnt > 0) b->order_cnt--;

    /* ST_BBO for EXECUTE/CANCEL. */
    if (!side && b->bid_valid && lv == b->bid_level) {
        if (lev_shares <= shares) {
            b->bid_valid = 0; b->bid_price = 0; b->bid_shares = 0;
        } else {
            b->bid_shares -= shares;
        }
    }
    if (side && b->ask_valid && lv == b->ask_level) {
        if (lev_shares <= shares) {
            b->ask_valid = 0; b->ask_price = 0; b->ask_shares = 0;
        } else {
            b->ask_shares -= shares;
        }
    }
}

/* DELETE path: invalidate map entry only. */
static void do_delete(book_t *b, uint64_t ref)
{
    unsigned idx = (unsigned)(ref & ORD_MASK);
    uint64_t tag = ref >> ORD_ADDR_W;

    b->del_cnt++;
    if (!b->map[idx].valid || b->map[idx].tag != tag) {
        b->drop_cnt++;
        return;
    }
    b->map[idx].valid = 0;
    if (b->order_cnt > 0) b->order_cnt--;
}

/* REPLACE path: mirrors the RTL (old entry invalidated, new order not
 * inserted — ST_LEV_UPDATE has no ACT_REPLACE arm). */
static void do_replace(book_t *b, uint64_t old_ref)
{
    unsigned idx = (unsigned)(old_ref & ORD_MASK);
    uint64_t tag = old_ref >> ORD_ADDR_W;

    b->rep_cnt++;
    if (!b->map[idx].valid || b->map[idx].tag != tag) {
        b->drop_cnt++;
        return;
    }
    b->map[idx].valid = 0;
}

/* ----------------------------------------------------------------------- */
/* ITCH decoding helpers (positions per the ITCH 5.0 spec)                  */
/* ----------------------------------------------------------------------- */

static inline uint16_t be16(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }
static inline uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8)  |  (uint32_t)p[3];
}
static inline uint64_t be64(const uint8_t *p)
{
    return ((uint64_t)be32(p) << 32) | be32(p + 4);
}

/* Apply one ITCH message body (body[0] is the type byte). */
static void apply_message(book_t *b, const uint8_t *body, unsigned len)
{
    uint8_t type;

    if (len < 1) return;
    type = body[0];

    switch (type) {
    case 'A': /* Add Order, no MPID: ref@11, side@19, shares@20, price@32 */
        if (len < 36) return;
        do_add(b, be64(body + 11), body[19] == 'S', be32(body + 20),
               be32(body + 32));
        break;
    case 'F': /* Add Order with MPID: price shifts to 36 */
        if (len < 40) return;
        do_add(b, be64(body + 11), body[19] == 'S', be32(body + 20),
               be32(body + 36));
        break;
    case 'E': /* Order Executed: ref@11, shares@19 */
        if (len < 31) return;
        /* The message carries no side.  itch_parse leaves d_side at its
         * reset value (0 = buy) for every non-ADD message, so the RTL
         * always takes the bid branch here; mirror that exactly. */
        do_reduce(b, be64(body + 11), 0, be32(body + 19), 1);
        break;
    case 'C': /* Order Executed With Price */
        if (len < 36) return;
        do_reduce(b, be64(body + 11), 0, be32(body + 19), 1);
        break;
    case 'X': /* Order Cancel */
        if (len < 23) return;
        do_reduce(b, be64(body + 11), 0, be32(body + 19), 0);
        break;
    case 'D': /* Order Delete */
        if (len < 19) return;
        do_delete(b, be64(body + 11));
        break;
    case 'U': /* Order Replace */
        if (len < 35) return;
        do_replace(b, be64(body + 11));
        break;
    case 'R': /* Stock Directory */
        break;
    default:
        break;
    }
}

/* ----------------------------------------------------------------------- */
/* Input walking                                                           */
/* ----------------------------------------------------------------------- */

typedef struct {
    FILE    *f;
    uint64_t bytes;
    uint64_t msgs;
} reader_t;

static int read_exact(FILE *f, uint8_t *buf, size_t n)
{
    size_t got = fread(buf, 1, n, f);
    return got == n ? 0 : -1;
}

/* Raw stream: {len[2] + body[len]} repeated. */
static void run_raw(reader_t *r, book_t *b, uint64_t max_msgs)
{
    uint8_t hdr[2];
    uint8_t body[65535];

    while (read_exact(r->f, hdr, 2) == 0) {
        unsigned len = be16(hdr);
        if (read_exact(r->f, body, len) != 0) break;
        apply_message(b, body, len);
        r->bytes += 2 + len;
        r->msgs++;
        if (max_msgs && r->msgs >= max_msgs) break;
    }
}

/* MoldUDP64 stream, project layout (matches scripts/pack_itch.py and
 * rtl/itch/mold64_reasm.v): per packet {session[8] + seq[2] + count[2]}
 * then count x {len[2] + body[len]}. */
static void run_mold64(reader_t *r, book_t *b, uint64_t max_msgs)
{
    uint8_t pkt[8 + 2 + 2];
    uint8_t hdr[2];
    uint8_t body[65535];

    while (read_exact(r->f, pkt, sizeof(pkt)) == 0) {
        unsigned count = be16(pkt + 10);
        unsigned i;

        r->bytes += sizeof(pkt);
        for (i = 0; i < count; i++) {
            unsigned len;
            if (read_exact(r->f, hdr, 2) != 0) return;
            len = be16(hdr);
            if (read_exact(r->f, body, len) != 0) return;
            apply_message(b, body, len);
            r->bytes += 2 + len;
            r->msgs++;
            if (max_msgs && r->msgs >= max_msgs) return;
        }
    }
}

/* ----------------------------------------------------------------------- */

static double now_ns(void)
{
#ifdef _WIN32
    /* Host-side syntax/benchmark build only; the measured baseline runs on
     * the board (Linux/armv7). */
    LARGE_INTEGER freq, cnt;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&cnt);
    return (double)cnt.QuadPart * 1e9 / (double)freq.QuadPart;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1e9 + (double)ts.tv_nsec;
#endif
}

int main(int argc, char **argv)
{
    const char *input = NULL;
    int raw = 0;
    uint64_t max_msgs = 0;
    book_t book;
    reader_t rd;
    double t0, t1;
    int i;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--input") && i + 1 < argc) {
            input = argv[++i];
        } else if (!strcmp(argv[i], "--raw")) {
            raw = 1;
        } else if (!strcmp(argv[i], "--max") && i + 1 < argc) {
            max_msgs = strtoull(argv[++i], NULL, 10);
        } else {
            fprintf(stderr, "unknown argument: %s\n", argv[i]);
            return 1;
        }
    }
    if (!input) {
        fprintf(stderr, "usage: %s --input <file> [--raw] [--max N]\n", argv[0]);
        return 1;
    }

    book_init(&book);
    rd.f = fopen(input, "rb");
    if (!rd.f) {
        fprintf(stderr, "open %s: %s\n", input, strerror(errno));
        return 2;
    }
    rd.bytes = 0;
    rd.msgs = 0;

    t0 = now_ns();
    if (raw) run_raw(&rd, &book, max_msgs);
    else     run_mold64(&rd, &book, max_msgs);
    t1 = now_ns();

    fclose(rd.f);

    printf("BASELINE-RESULT: msgs=%" PRIu64 " bytes=%" PRIu64
           " elapsed_ns=%.0f ns_per_msg=%.2f msg_per_s=%.2f\n",
           rd.msgs, rd.bytes, t1 - t0,
           rd.msgs ? (t1 - t0) / (double)rd.msgs : 0.0,
           (t1 - t0) > 0 ? (double)rd.msgs * 1e9 / (t1 - t0) : 0.0);
    printf("BOOK-COUNTERS: add=%u exe=%u can=%u del=%u rep=%u drop=%u "
           "orders=%u levels=%u\n",
           book.add_cnt, book.exe_cnt, book.can_cnt, book.del_cnt,
           book.rep_cnt, book.drop_cnt, book.order_cnt, book.level_cnt);
    printf("BBO: bid_price=%u bid_shares=%u bid_valid=%u "
           "ask_price=%u ask_shares=%u ask_valid=%u\n",
           book.bid_price, book.bid_shares, book.bid_valid,
           book.ask_price, book.ask_shares, book.ask_valid);
    printf("BASELINE-DONE\n");
    return 0;
}
