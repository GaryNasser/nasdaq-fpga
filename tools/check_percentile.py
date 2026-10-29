"""Verify the percentile arithmetic behind the published T1 figures.

The report's headline latency numbers - p50 210.5 ns, p95 1052.6 ns, p99 1136.8 ns -
are produced by `_hist_percentile` in the driver, which converts a 256-bin histogram of
8-cycle buckets into a nanosecond figure.

Nothing tested that function. `tb_ts_hist` proves the histogram separates latencies
(MAX > MIN); it does not prove the percentile derived from it. `check_internal_consistency`
compares numbers between documents; `check_t1_units` checks the bucket width. Neither
calls the arithmetic.

An off-by-one in the bucket index would shift every published latency by 42 ns at
190 MHz - about 20% of p50 - while all existing checks stayed green.

This runs the function against five histograms whose answers are known by hand:

    all in bucket 0, p50   -> upper edge of bucket 0
    all in bucket 0, p99   -> same
    all in bucket 10, p50  -> upper edge of bucket 10
    50% in bucket 20, p50  -> upper edge of bucket 20
    empty histogram        -> None, not a number

The functions are extracted from the driver source and executed directly, so the check
does not need PYNQ or a board.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
DRV = os.path.join(REPO, "board", "load_overlay.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(DRV):
    print("PERCENTILE-FAIL (no driver)")
    sys.exit(1)

src = io.open(DRV, encoding="utf-8").read()

ns = {"io": io, "re": re}
for name in ("TS_BIN_CYCLES", "PL_CLK_MHZ"):
    m = re.search(r"^%s\s*=\s*([\d.]+)" % name, src, re.M)
    if m:
        ns[name] = float(m.group(1))

missing = [k for k in ("TS_BIN_CYCLES", "PL_CLK_MHZ") if k not in ns]
if missing:
    print("PERCENTILE-FAIL (%s not found in the driver)" % ", ".join(missing))
    sys.exit(1)


def grab(name):
    i = src.find("def %s(" % name)
    if i == -1:
        return None
    j = src.find("\ndef ", i + 1)
    return src[i:j if j != -1 else len(src)]


for fn in ("_cycles_to_ns", "_hist_percentile"):
    body = grab(fn)
    if body is None:
        print("PERCENTILE-FAIL (%s missing)" % fn)
        sys.exit(1)
    exec(body, ns)

_cycles_to_ns = ns["_cycles_to_ns"]
_hist_percentile = ns["_hist_percentile"]
BIN = int(ns["TS_BIN_CYCLES"])
NB = 256

print("percentile arithmetic")
print("  TS_BIN_CYCLES = %d (%.3f ns at %.0f MHz)"
      % (BIN, _cycles_to_ns(BIN), ns["PL_CLK_MHZ"]))
print()


def hist(bucket=None, counts=None):
    h = [0] * NB
    if bucket is not None:
        h[bucket] = 1000
    if counts:
        for b, c in counts.items():
            h[b] = c
    return h


CASES = [
    ("all in bucket 0, p50", lambda: _hist_percentile(hist(0), 50),
     lambda: _cycles_to_ns(BIN)),
    ("all in bucket 0, p99", lambda: _hist_percentile(hist(0), 99),
     lambda: _cycles_to_ns(BIN)),
    ("all in bucket 10, p50", lambda: _hist_percentile(hist(10), 50),
     lambda: _cycles_to_ns(11 * BIN)),
    ("50% in bucket 20, p50",
     lambda: _hist_percentile(hist(counts={0: 100, 20: 800, 100: 100}), 50),
     lambda: _cycles_to_ns(21 * BIN)),
    ("empty histogram", lambda: _hist_percentile([0] * NB, 50), lambda: None),
]

fails = []
print("%-26s %-14s %-14s %s" % ("case", "computed", "expected", ""))
print("-" * 70)
for name, got_fn, want_fn in CASES:
    try:
        got = got_fn()
    except Exception as e:  # noqa: BLE001
        fails.append("%s raised %s" % (name, type(e).__name__))
        print("%-26s %-14s %-14s RAISED" % (name, "-", "-"))
        continue
    want = want_fn()
    ok = (got == want)
    if not ok:
        fails.append("%s: got %r want %r" % (name, got, want))
    print("%-26s %-14s %-14s %s"
          % (name, "None" if got is None else "%.3f" % got,
             "None" if want is None else "%.3f" % want, "ok" if ok else "WRONG"))

print()
if fails:
    print("PERCENTILE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("PERCENTILE-PASS")
