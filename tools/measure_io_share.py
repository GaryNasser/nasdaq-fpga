"""Measure how much of the baseline's time is file I/O rather than parsing.

The headline 3.10x compares two different quantities:

    PL  : cycles between event ingress and book acceptance   (no I/O at all)
    A9  : wall clock around run_raw(), which calls fread()   (includes I/O)

On this host the effect is large. This generates an instrumented copy of the
baseline (in TEMP; the committed source is untouched), times a standalone read of
the same file with the same portable timer the baseline already uses
(QueryPerformanceCounter on _WIN32, clock_gettime elsewhere), and reports the
split.

The result is a BOUND, not a correction: the A9's SD/eMMC read share is not
knowable from here, so the honest output is "the PL figure excludes I/O, the A9
figure includes it, and here is why that inflates the ratio".
"""
import io
import os
import re
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
SRC = os.path.join(REPO, "sw", "baseline", "itch_book_baseline.c")
WORK = os.path.join(os.environ["TEMP"], "nasdaq_baseline")
RAW = os.path.join(WORK, "raw.bin")

os.makedirs(WORK, exist_ok=True)
text = io.open(SRC, encoding="utf-8", errors="surrogateescape").read()

if "g_io_bytes" not in text:
    text = text.replace(
        "static int read_exact(FILE *f, uint8_t *buf, size_t n)",
        "static uint64_t g_io_bytes = 0;\n"
        "static int read_exact(FILE *f, uint8_t *buf, size_t n)", 1)
    text = text.replace("  size_t got = fread(buf, 1, n, f);",
                        "  size_t got = fread(buf, 1, n, f);\n  g_io_bytes += got;", 1)
if "IO-BYTES" not in text:
    text = text.replace(
        '  printf("BASELINE-DONE\\n");',
        '  printf("IO-BYTES: %" PRIu64 "\\n", g_io_bytes);\n  printf("BASELINE-DONE\\n");', 1)

variant = os.path.join(WORK, "itch_book_baseline_io.c")
io.open(variant, "w", encoding="utf-8", errors="surrogateescape",
        newline="\n").write(text)

exe = os.path.join(WORK, "baseline_io.exe")
r = subprocess.run(["gcc", "-O3", "-o", exe, variant],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True)
if r.returncode != 0:
    print(r.stderr[-1500:])
    sys.exit(1)
print("instrumented baseline built")

probe_src = r"""
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
static double now_ms(void){LARGE_INTEGER f,c;QueryPerformanceFrequency(&f);
QueryPerformanceCounter(&c);return 1000.0*(double)c.QuadPart/(double)f.QuadPart;}
#else
#include <time.h>
static double now_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);
return t.tv_sec*1000.0+t.tv_nsec/1e6;}
#endif
int main(int argc,char**argv){
  FILE*f=fopen(argv[1],"rb");
  if(!f){perror("open");return 1;}
  fseek(f,0,SEEK_END); long n=ftell(f); fseek(f,0,SEEK_SET);
  unsigned char*p=malloc(n);
  fread(p,1,n,f);
  double best=1e9;
  for(int i=0;i<7;i++){
    fseek(f,0,SEEK_SET);
    double t0=now_ms();
    size_t got=fread(p,1,n,f);
    double t1=now_ms();
    (void)got;
    if(t1-t0<best) best=t1-t0;
  }
  printf("IO-PROBE bytes=%ld best_read_ms=%.3f\n",n,best);
  fclose(f); free(p);
  return 0;
}
"""
probe_c = os.path.join(WORK, "io_probe.c")
io.open(probe_c, "w", encoding="utf-8", newline="\n").write(probe_src)
probe_exe = os.path.join(WORK, "io_probe.exe")
r = subprocess.run(["gcc", "-O3", "-o", probe_exe, probe_c],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True)
probe_ms = None
if r.returncode == 0:
    r = subprocess.run([probe_exe, RAW], capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True)
    m = re.search(r"best_read_ms=([\d.]+)", r.stdout)
    if m:
        probe_ms = float(m.group(1))
        print("standalone read: %.3f ms" % probe_ms)
else:
    print("probe build failed:")
    print(r.stderr[-800:])

best_ns = None
best_io = None
for _ in range(7):
    r = subprocess.run([exe, "--input", RAW, "--raw"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True)
    m = re.search(r"elapsed_ns=(\d+)", r.stdout)
    if not m:
        continue
    ns = int(m.group(1))
    if best_ns is None or ns < best_ns:
        best_ns = ns
        for l in r.stdout.splitlines():
            if l.startswith("IO-BYTES:"):
                best_io = int(l.split(":")[1].strip())

print()
print("baseline timed run : %.3f ms (best of 7), read %s bytes"
      % (best_ns / 1e6, best_io))

if probe_ms is not None and best_ns:
    io_ns = probe_ms * 1e6
    frac = io_ns / best_ns
    print()
    print("SPLIT ON THIS HOST")
    print("  read  %7.3f ms  %5.1f%%" % (probe_ms, 100 * frac))
    print("  parse %7.3f ms  %5.1f%%"
          % ((best_ns - io_ns) / 1e6, 100 * (1 - frac)))
    print()
    print("WHAT THIS MEANS FOR THE 3.10x FIGURE")
    print("  The PL number is cycles between event ingress and book acceptance:")
    print("  it contains no file I/O at all. The A9 number is a wall clock")
    print("  wrapped around a loop that fread()s its input. So the ratio")
    print("  compares compute-only against compute-plus-I/O, and is an")
    print("  OPTIMISTIC bound rather than a like-for-like speedup.")
    print()
    print("  On this host %.0f%% of the timed run is I/O. The A9's share is not"
          % (100 * frac))
    print("  knowable from here (SD/eMMC vs SSD), which is exactly why the")
    print("  honest claim is a bound. A future on-board measurement should")
    print("  either preload the input or time the PL side through DMA too.")

r = subprocess.run([exe, "--input", RAW, "--raw"], capture_output=True,
                   text=True, encoding="utf-8", errors="replace", shell=True)
line = next((l for l in r.stdout.splitlines() if l.startswith("BOOK-COUNTERS")), "")
GOLD = ("add=15334 exe=7 can=12518 del=15291 rep=238 drop=12826 "
        "orders=320 levels=95")
ok = line.split("BOOK-COUNTERS:", 1)[-1].strip() == GOLD
print()
print("counters still match golden: %s" % ("YES" if ok else "NO"))
print("IO-SHARE-%s" % ("OK" if ok else "FAIL"))
sys.exit(0 if ok else 1)
