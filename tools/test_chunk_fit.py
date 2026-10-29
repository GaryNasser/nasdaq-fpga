"""Test the sweep's REAL fit function, imported rather than reimplemented.

The previous version had its own copy of the least-squares code, so it tested the copy.
If chunk_sweep.py's fit were wrong, this test would still pass - which is the defect
pattern this project has hit repeatedly (a test that exercises a duplicate of the subject).

Now it imports fit_overhead from chunk_sweep and checks it against synthetic data with
known answers:

    t(n) = fixed + chunks * per_desc + n / pipeline_rate

Four cases, including a zero slope (a legitimate result) and a negative one (a
contradiction the tool must report rather than interpret).
"""
import importlib.util
import io
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SWEEP = r"D:\agent\nasdaq-fpga\tools\chunk_sweep.py"

spec = importlib.util.spec_from_file_location("chunk_sweep", SWEEP)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fit_overhead = mod.fit_overhead
PIPELINE_RATE_MBPS = mod.PIPELINE_RATE_MBPS
MB = 1 << 20

CASES = [
    ("known per-descriptor cost", 0.002, 400e-6, 29.0),
    ("zero per-descriptor cost", 0.002, 0.0, 29.0),
    ("large fixed, small per-desc", 0.050, 50e-6, 29.0),
    ("negative slope (contradiction)", 0.020, -100e-6, 29.0),
]


def synth(fixed, per_desc, size_mb):
    n = int(size_mb * MB)
    pts = []
    for mb in (1, 2, 4, 8):
        chunks = (n + mb * MB - 1) // (mb * MB)
        t_pipe = n / (PIPELINE_RATE_MBPS * 1e6)
        overhead = fixed + chunks * per_desc
        pts.append((chunks, overhead))
    return pts


print("fit recovery test (importing chunk_sweep.fit_overhead)")
print()

fails = 0
for name, fixed, per_desc, size_mb in CASES:
    pts = synth(fixed, per_desc, size_mb)
    got_pd, got_fixed = fit_overhead(pts)
    ok_pd = abs(got_pd - per_desc) < 1e-9
    ok_fx = abs(got_fixed - fixed) < 1e-9
    if not (ok_pd and ok_fx):
        fails += 1
    print("  %-32s per-desc %9.1f us (want %9.1f) %s  fixed %.4f s %s"
          % (name, got_pd * 1e6, per_desc * 1e6, "ok" if ok_pd else "WRONG",
             got_fixed, "ok" if ok_fx else "WRONG"))

# Degenerate inputs must return None rather than divide by zero.
print()
deg = [
    ("single point", [(3, 0.01)]),
    ("identical chunk counts", [(5, 0.01), (5, 0.02)]),
]
for name, pts in deg:
    pd, fx = fit_overhead(pts)
    ok = pd is None and fx is None
    if not ok:
        fails += 1
    print("  %-32s returns None: %s" % (name, ok))

print()
total = len(CASES) + len(deg)
print("  %d of %d cases correct" % (total - fails, total))
if fails:
    print("CHUNK-FIT-FAIL")
    sys.exit(1)
print("CHUNK-FIT-PASS")
