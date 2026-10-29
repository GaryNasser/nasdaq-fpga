"""Make a one-packet variant of tb_fullchain and run it through the whole chain.

Round 136 measured on hardware: one 49-message packet gives messages=49, add=0, drop=0. The
reassembler delivers and the book counts nothing.

tb_fullchain replays 850 packets against the golden 15334 Adds, so a first-packet loss is 8 out of
15334 - invisible. This variant replays packet 1 alone and compares against THAT packet's own
expected counts, which the C baseline gives.

If the variant reports add=0, the defect reproduces in simulation and can be debugged there. If it
reports add=8, the simulation does not reproduce it and the board's behaviour has another cause.

Either answer is worth more than the four fixes tested against a bench that could not show the
failure.
"""
import io
import os
import re
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
TB = os.path.join(REPO, "tools", "tb_fullchain.v")
WORK = os.path.join(os.environ.get("TEMP", "."), "nasdaq_firstpkt")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Expected counters for packet 1 alone, from the C baseline.
pkt1 = os.path.join(REPO, "data", "_pkt1.mold64")
exe = os.path.join(WORK, "baseline.exe")
os.makedirs(WORK, exist_ok=True)
b = subprocess.run(["gcc", "-O2", "-o", exe, os.path.join(REPO, "sw", "baseline",
                                                           "itch_book_baseline.c")],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
if b.returncode != 0:
    print("baseline build failed")
    sys.exit(1)
r = subprocess.run([exe, "--input", pkt1], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
m = re.search(r"BOOK-COUNTERS:\s*add=(\d+)\s+exe=(\d+)\s+can=(\d+)\s+del=(\d+)\s+"
              r"rep=(\d+)\s+drop=(\d+)\s+orders=(\d+)\s+levels=(\d+)", r.stdout or "")
if not m:
    print("baseline gave no counters")
    sys.exit(1)
add, exe_c, can, dele, rep, drop, orders, levels = (int(x) for x in m.groups())
print("packet 1 alone, per the C baseline")
print("  add=%d exe=%d can=%d del=%d rep=%d drop=%d orders=%d levels=%d"
      % (add, exe_c, can, dele, rep, drop, orders, levels))
print()

src = io.open(TB, encoding="utf-8").read()

subs = [
    ("parameter NPKT        = 850;", "parameter NPKT        = 1;"),
    ("parameter TOTAL_BYTES = 1237116;", "parameter TOTAL_BYTES = 1463;"),
    ("localparam EXP_ADD = 32'd15334;", "localparam EXP_ADD = 32'd%d;" % add),
    ("localparam EXP_EXE = 32'd7;", "localparam EXP_EXE = 32'd%d;" % exe_c),
    ("localparam EXP_CAN = 32'd12518;", "localparam EXP_CAN = 32'd%d;" % can),
    ("localparam EXP_DEL = 32'd15291;", "localparam EXP_DEL = 32'd%d;" % dele),
    ("localparam EXP_REP = 32'd238;", "localparam EXP_REP = 32'd%d;" % rep),
    ("localparam EXP_DROP= 32'd12826;", "localparam EXP_DROP= 32'd%d;" % drop),
    ("localparam EXP_ORD = 32'd320;", "localparam EXP_ORD = 32'd%d;" % orders),
    ("localparam EXP_LEV = 32'd95;", "localparam EXP_LEV = 32'd%d;" % levels),
]

variant = src
missed = []
for old, new in subs:
    if old not in variant:
        missed.append(old)
        continue
    variant = variant.replace(old, new, 1)

if missed:
    print("anchors not found:")
    for x in missed:
        print("  %s" % x)
    sys.exit(1)

# Rename the module so both can coexist.
variant = variant.replace("module tb_fullchain;", "module tb_first_packet;", 1)
variant = variant.replace("FULLCHAIN-", "FIRSTPKT-")
assert variant != src

out_tb = os.path.join(WORK, "tb_first_packet.v")
io.open(out_tb, "w", encoding="utf-8", newline="\n").write(variant)
print("variant written: tb_first_packet (NPKT=1, TOTAL_BYTES=1463)")
print()

env = dict(os.environ)
env["PATH"] = r"D:\Xilinx\Vivado\2024.1\bin;" + env.get("PATH", "")
rtl = [os.path.join(REPO, "rtl", "itch", f) for f in
       ("mold64_reasm.v", "itch_parse.v", "order_book.v", "ts_hist.v")]
for cmd in ([("xvlog.bat")] + rtl + [out_tb],
            ["xelab.bat", "-debug", "typical", "tb_first_packet", "-s", "tb_first_packet"]):
    r = subprocess.run(cmd, cwd=WORK, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, shell=True)
    if r.returncode != 0:
        print("compile/elaborate failed:")
        for l in ((r.stdout or "") + (r.stderr or "")).splitlines()[:8]:
            print("  " + l.strip()[:100])
        sys.exit(1)

r = subprocess.run(["xsim.bat", "tb_first_packet", "-R"], cwd=WORK, capture_output=True,
                   text=True, encoding="utf-8", errors="replace", env=env, shell=True)
print("simulation")
print()
for l in (r.stdout or "").splitlines():
    if "FIRSTPKT" in l or "FULLCHAIN" in l:
        print("  %s" % l.strip()[:104])
