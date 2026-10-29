"""Independently reproduce the golden book counters with the C baseline.

The golden reference has been quoted since M7 but was produced ONCE, on the
board, in 2026-10-18. With the board unreachable, the whole golden-comparison
methodology rests on that single historical artifact. This re-derives it locally
so the claim is checked rather than trusted.

It also pins down the two input formats, which differ by exactly 850x12 = 10200
bytes and are trivially confusable:

    MoldUDP64 file  1237116 B  (12-byte header per packet)   --input <file>
    raw msg stream  1226916 B  (len[2] + body per message)   --input <file> --raw

The recorded A9 runs used --raw. Using the other format yields the same counters
but a different bytes= field, which would silently invalidate a comparison.
"""
import io
import os
import re
import shutil
import struct
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
SRC = os.path.join(REPO, "sw", "baseline", "itch_book_baseline.c")
DATA = os.path.join(REPO, "data", "itch_loc6836.mold64")
WORK = os.path.join(os.environ["TEMP"], "nasdaq_baseline")
# Read the expectation from the REPORT, not from a constant. A constant proves the C program is
# deterministic; only the report's own line proves the report quotes what the program prints.
_rep = io.open(os.path.join(REPO, "docs", "final-report.md"),
               encoding="utf-8", errors="surrogateescape").read()
_m = re.search(r"BOOK-COUNTERS:\s*(add=.*?levels=\d+)", _rep)
if not _m:
    print("BASELINE-REPRO-FAIL (the report quotes no BOOK-COUNTERS line)")
    sys.exit(1)
GOLD = _m.group(1).strip()
print("  expectation taken from the report: %s" % GOLD[:72])

os.makedirs(WORK, exist_ok=True)
exe = os.path.join(WORK, "baseline.exe")

print("building the C baseline with the local gcc")
r = subprocess.run(["gcc", "-O3", "-o", exe, SRC],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True)
if r.returncode != 0:
    print(r.stdout[-1500:])
    print(r.stderr[-1500:])
    sys.exit(1)
print("  build OK")

# --- MoldUDP64 form ------------------------------------------------------
r = subprocess.run([exe, "--input", DATA], capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True)
udp_line = next((l for l in r.stdout.splitlines() if l.startswith("BOOK-COUNTERS")), "")
udp_bytes = None
for l in r.stdout.splitlines():
    if l.startswith("BASELINE-RESULT:"):
        for f in l.split():
            if f.startswith("bytes="):
                udp_bytes = int(f.split("=")[1])
print()
print("MoldUDP64 form: bytes=%s" % udp_bytes)

# --- raw form ------------------------------------------------------------
raw_path = os.path.join(WORK, "raw.bin")
d = io.open(DATA, "rb").read()
out = bytearray()
off = 0
nmsg = 0
while off + 12 <= len(d):
    cnt = struct.unpack(">H", d[off + 10:off + 12])[0]
    m = off + 12
    for _ in range(cnt):
        ln = struct.unpack(">H", d[m:m + 2])[0]
        out += d[m:m + 2 + ln]
        m += 2 + ln
        nmsg += 1
    off = m
io.open(raw_path, "wb").write(bytes(out))
print("raw form      : %d bytes, %d messages" % (len(out), nmsg))

r = subprocess.run([exe, "--input", raw_path, "--raw"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True)
raw_line = next((l for l in r.stdout.splitlines() if l.startswith("BOOK-COUNTERS")), "")

def counters(line):
    return line.split("BOOK-COUNTERS:", 1)[1].strip() if ":" in line else ""

fails = []
print()
for label, line, want_bytes in (("MoldUDP64", udp_line, 1237116),
                                ("raw", raw_line, 1226916)):
    got = counters(line)
    ok = (got == GOLD)
    print("%-9s counters %s" % (label, "MATCH golden" if ok else "DIFFER"))
    if not ok:
        print("   got : %s" % got)
        print("   want: %s" % GOLD)
        fails.append("%s counters differ" % label)

if udp_bytes != 1237116:
    fails.append("MoldUDP64 bytes=%s, expected 1237116" % udp_bytes)
if len(out) != 1226916:
    fails.append("raw stream %d bytes, expected 1226916" % len(out))
print()
print("byte accounting: MoldUDP64 %s (want 1237116), raw %d (want 1226916)"
      % (udp_bytes, len(out)))

print()
if fails:
    print("BASELINE-REPRO-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("BASELINE-REPRO-PASS")
