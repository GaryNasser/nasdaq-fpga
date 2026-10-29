import struct
"""Run the chunk-size sweep on the board and fit the per-descriptor cost.

Usage (on the board host, or remotely):

    python tools/chunk_sweep.py --input /home/xilinx/itch_29mb.mold64 [--run]

Without --run it prints the plan and exits, so it is safe to invoke before the board is up.

What it does:

  for each buffer-mb in {1, 2, 4, 8}:
      run the driver twice with --pipeline
      keep the faster MB/s (matching the A9 baseline's best-of-N method)

  then fit:
      t_total = t_fixed + chunks * per_desc + bytes / pipeline_rate

  and report per_desc in microseconds plus its share of the total time.

Why best-of-two: the first transfer after loading the file pays cold-cache latency, which
is visible in the A9 runs as a 52% spread (927.35 to 1414.30 ns/message). Taking the
fastest removes that confound without hiding per-descriptor cost, which is a steady-state
property.
"""
import argparse
import io
import os
import re
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
DRIVER = os.path.join(REPO, "board", "load_overlay.py")
PIPELINE_RATE_MBPS = 94.5          # 28.252 B/msg x 3,344,390 msg/s, exactly
REFERENCE_BYTES = 1237116

MBPS = re.compile(r"([\d.]+)\s*MB/s")
PACKETS = re.compile(r"(\d+)\s*/\s*(\d+)\s*packets")


BOARD = "pynq-z2-codex"
REMOTE_DIR = "/home/xilinx/overlays/nasdaq"


def _count_messages(path):
    """Sum the MoldUDP64 message counts so --messages matches the file.

    Layout: 8 session + 2 sequence + 2 count, then count x (2 length + payload).

    Verified against the report's figures for data/itch_1m.mold64: 20,042 packets, 1,000,000 messages.
    """
    total = 0
    with open(path, "rb") as f:
        data = f.read()
    p = 0
    while p + 12 <= len(data):
        cnt = struct.unpack(">H", data[p + 10:p + 12])[0]
        p += 12
        total += cnt
        for _ in range(cnt):
            if p + 2 > len(data):
                return total
            ln = struct.unpack(">H", data[p:p + 2])[0]
            p += 2 + ln
    return total

def _ssh(cmd, timeout=120):
    return subprocess.run(["ssh", "-o", "ConnectTimeout=15", BOARD, cmd],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def remote_input(inp):
    """Resolve where this capture lives on the board, or copy it there.

    Rounds 100+ wrote the driver's cwd (REMOTE_DIR) into the command but passed only the
    basename, so every attempt failed `FileNotFoundError` while the file sat one directory
    up in /home/xilinx. Both locations are checked, and a missing file is copied to
    REMOTE_DIR rather than reported as a measurement failure.
    """
    base = os.path.basename(inp)
    for path in (os.path.join(REMOTE_DIR, base), "/home/xilinx/" + base):
        r = _ssh("test -f %s && echo FOUND" % path, timeout=60)
        if "FOUND" in (r.stdout or ""):
            return path
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=15", BOARD,
                        "cat > %s" % os.path.join(REMOTE_DIR, base)],
                       stdin=open(inp, "rb"), capture_output=True, timeout=900)
    if r.returncode != 0:
        return None
    return os.path.join(REMOTE_DIR, base)


def run_once(inp, mb, extra=()):
    """Run the driver's pipeline mode at one chunk size ON THE BOARD.

    load_overlay.py is a PYNQ driver: it imports numpy/pynq/XRT and talks to /dev/mem.
    Running it on the development host fails with ModuleNotFoundError, and on a host that
    happened to have those packages it would measure the host rather than the board.

    Mirrors board_recover.py: one ssh per chunk size, the PYNQ venv interpreter, XILINX_XRT
    set, and the same output parsing.
    """
    rpath = remote_input(inp)
    if rpath is None:
        return None, "input could not be placed on the board: %s" % os.path.basename(inp)
    remote = ("cd %s && sudo -n env XILINX_XRT=/usr "
              "/usr/local/share/pynq-venv/bin/python load_overlay.py "
              "--pipeline --input %s --buffer-mb %d --messages %d %s"
               % (REMOTE_DIR, rpath, mb, _count_messages(inp),
                  " ".join(extra)))
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=15", BOARD, remote],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    out = (r.stdout or "") + (r.stderr or "")
    m = MBPS.search(out)
    return (float(m.group(1)) if m else None), out


def fit_overhead(points):
    """Least squares on overhead = fixed + per_desc * chunks.

    points: list of (chunks, overhead_seconds)

    Returns (per_desc, fixed), or (None, None) when every point has the same chunk count
    and the slope is therefore undetermined.

    Kept as a module-level function so tools/test_chunk_fit.py exercises THIS code rather
    than a copy of it.
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    n_pts = len(xs)
    if n_pts < 2:
        return None, None
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n_pts * sxx - sx * sx
    if denom == 0:
        return None, None
    per_desc = (n_pts * sxy - sx * sy) / denom
    fixed = (sy - per_desc * sx) / n_pts
    return per_desc, fixed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="29 MB tier MoldUDP64 capture")
    ap.add_argument("--sizes", default="1,2,4,8")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--run", action="store_true", help="actually run the board")
    args = ap.parse_args()

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    if not os.path.exists(args.input):
        print("CHUNK-SWEEP-FAIL: input not found: %s" % args.input)
        return 2
    total_bytes = os.path.getsize(args.input)

    print("chunk-size sweep (runs on the board over ssh)")
    print()
    print("  input      : %s" % args.input)
    if total_bytes:
        print("  size       : %d B = %.2f MB" % (total_bytes, total_bytes / 1048576))
        if total_bytes <= 4 * 1024 * 1024:
            print("  WARNING    : under 4 MB - at most %d chunks; the reference capture"
                  % max(1, total_bytes // (1 << 20)))
            print("               (1.18 MB) is too small for a meaningful slope.")
    print("  chunk sizes: %s MB" % sizes)
    print("  repeats    : %d per size (fastest kept)" % args.repeat)
    print()

    if not args.run:
        print("  dry run - pass --run to execute on the board")
        for mb in sizes:
            chunks = (total_bytes + mb * (1 << 20) - 1) // (mb * (1 << 20)) \
                if total_bytes else "?"
            print("     buffer-mb=%-2d -> %s chunk(s)" % (mb, chunks))
        return 0

    # One connectivity probe before the sweep. Without it an unreachable board produces
    # four identical timeouts and an INCONCLUSIVE verdict that reads like a measurement
    # problem rather than a connectivity one.
    probe = subprocess.run(["ssh", "-o", "ConnectTimeout=12", BOARD, "echo ALIVE"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
    if "ALIVE" not in (probe.stdout or ""):
        print("CHUNK-SWEEP-UNREACHABLE: %s did not answer" % BOARD)
        tail = [l for l in (probe.stderr or "").strip().splitlines() if l.strip()][-1:]
        if tail:
            print("  %s" % tail[0].strip()[:100])
        print("  the board needs a power cycle; see docs/RUNBOOK.md section 0")
        return 2

    results = []
    for mb in sizes:
        best = None
        for i in range(args.repeat):
            rate, out = run_once(args.input, mb)
            if rate is None:
                # Surface why, rather than silently skipping.
                tail = [l for l in out.strip().splitlines() if l.strip()][-4:]
                print("  buffer-mb=%-2d run %d: no rate found" % (mb, i + 1))
                for l in tail:
                    print("     | " + l[:100])
                break
            if best is None or rate > best:
                best = rate
        if best is not None:
            results.append((mb, best))
            print("  buffer-mb=%-2d -> %.1f MB/s" % (mb, best))
        sys.stdout.flush()

    if len(results) < 2:
        print()
        print("CHUNK-SWEEP-INCONCLUSIVE (need at least two chunk sizes)")
        return 1

    # Fit: t(n) = fixed + chunks * per_desc + n / pipeline_rate
    print()
    print("  fit")
    print("  ---")
    rows = []
    for mb, rate in results:
        n = total_bytes
        chunks = (n + mb * (1 << 20) - 1) // (mb * (1 << 20))
        t_total = n / (rate * 1e6)
        t_pipeline = n / (PIPELINE_RATE_MBPS * 1e6)
        overhead = t_total - t_pipeline
        rows.append((mb, chunks, t_total, overhead))
        print("     %-2d MB: %2d chunks, total %.3f s, pipeline %.3f s, "
              "overhead %.3f s" % (mb, chunks, t_total, t_pipeline, overhead))

    per_desc, fixed = fit_overhead([(r[1], r[3]) for r in rows])
    if per_desc is None:
        print()
        print("CHUNK-SWEEP-INCONCLUSIVE (all runs used the same chunk count)")
        return 1

    print()
    print("     per-descriptor cost : %.1f us" % (per_desc * 1e6))
    print("     fixed cost          : %.3f s" % fixed)
    print()
    # Three cases, not two: a zero slope means the chunk count has no measurable effect,
    # which is a result (the per-descriptor cost is below resolution), not a negative one.
    if per_desc > 0:
        print("     POSITIVE slope: overhead grows with chunk count, as expected for")
        print("     per-descriptor cost. At %d chunks this is %.3f s of the %.3f s total."
              % (rows[0][1], per_desc * rows[0][1], rows[0][2]))
    elif per_desc == 0:
        print("     ZERO slope: chunk count has no measurable effect. Either the")
        print("     per-descriptor cost is below this measurement's resolution, or the")
        print("     driver is not paying it per chunk.")
    else:
        print("     NEGATIVE slope: the model does not fit - larger buffers are not")
        print("     simply fewer descriptors. Report this; do not force an interpretation.")
    print()
    print("CHUNK-SWEEP-PASS")
    return 0


class _Tee:
    """Print to the console and record every line."""

    def __init__(self, stream):
        self.stream = stream
        self.lines = []

    def write(self, s):
        self.stream.write(s)
        self.lines.append(s)
        return len(s)

    def flush(self):
        self.stream.flush()


def _run_and_save(argv=None):
    """Run main(), then write the transcript to docs/measurements/.

    Rounds 103-104 found six headline figures with no file behind them, all console output that
    was never saved. The chunk sweep produces the DMA throughput that closes the last PENDING
    deliverable, so its numbers must land in a file.
    """
    import datetime
    import hashlib

    tee = _Tee(sys.stdout)
    real = sys.stdout
    sys.stdout = tee
    try:
        rc = main()
    finally:
        sys.stdout = real

    try:
        meas = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "docs", "measurements")
        os.makedirs(meas, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        rec = os.path.join(meas, "chunk-sweep-%s.txt" % stamp)
        bit = os.path.join(os.path.dirname(meas), "..", "vivado", "out",
                           "nasdaq.bit")
        bit_md5 = None
        if os.path.exists(bit):
            bit_md5 = hashlib.md5(open(bit, "rb").read()).hexdigest().upper()
        with io.open(rec, "w", encoding="utf-8", newline="\n") as f:
            f.write("# chunk_sweep run %s\n" % stamp)
            f.write("# argv: %s\n" % " ".join(sys.argv))
            f.write("# bitstream md5: %s\n" % (bit_md5 or "missing"))
            f.write("# exit: %d\n" % rc)
            f.write("#\n# ---- transcript ----\n")
            f.write("".join(tee.lines))
        print("output saved to %s" % os.path.relpath(rec))
    except Exception as exc:                        # never let logging break the run
        print("WARNING: could not save the transcript: %s" % exc)

    return rc


if __name__ == "__main__":
    sys.exit(_run_and_save())
