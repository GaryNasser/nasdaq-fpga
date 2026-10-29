"""Run either real capture through the reassembler and report exact counts.

The single most valuable test in this project: synthetic packets hid a
4096-byte periodic packet-abandonment bug for many rounds, and only real
captured traffic exposed it. This script generates the $readmemh image for a
chosen capture, builds an appropriately sized testbench, runs it, and compares
the DUT's counters against an independent parse of the same file.

Usage:
    python tools/run_realfile.py            # itch_loc6836 (850 packets)
    python tools/run_realfile.py 1m         # itch_1m    (20042 packets)
"""
import io
import os
import re
import struct
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIVADO_BIN = os.environ.get("VIVADO_BIN", r"D:\Xilinx\Vivado\2024.1\bin")
XVLOG = os.path.join(VIVADO_BIN, "xvlog.bat")
XELAB = os.path.join(VIVADO_BIN, "xelab.bat")
XSIM = os.path.join(VIVADO_BIN, "xsim.bat")

WHICH = (sys.argv[1] if len(sys.argv) > 1 else "").lower()

if WHICH == "1m":
    SRC = os.path.join(REPO, "data", "itch_1m.mold64")
    MAXB = 29300000
    POST = 20000000
else:
    SRC = os.path.join(REPO, "data", "itch_loc6836.mold64")
    MAXB = 1300000
    POST = 4000000


def parse(path):
    """Independent MoldUDP64 walk: returns (packets, messages, bytes)."""
    data = open(path, "rb").read()
    off = 0
    pkts = 0
    msgs = 0
    while off + 12 <= len(data):
        cnt = struct.unpack(">H", data[off + 10:off + 12])[0]
        m = off + 12
        for _ in range(cnt):
            ml = struct.unpack(">H", data[m:m + 2])[0]
            m += 2 + ml
            msgs += 1
        pkts += 1
        off = m
    return pkts, msgs, len(data)


pkts, msgs, nbytes = parse(SRC)
print("reference parse: %d packets, %d messages, %d bytes" % (pkts, msgs, nbytes))

WORK = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", "/tmp")), "nasdaq_realfile")
os.makedirs(WORK, exist_ok=True)
HEX = os.path.join(WORK, "img.hex")

with open(SRC, "rb") as f:
    data = f.read()
with io.open(HEX, "w", encoding="ascii", newline="\n") as f:
    for b in data:
        f.write("%02x\n" % b)
print("wrote image: %s" % HEX)

# Derive the testbench from the committed one, resizing it for this capture.
base = io.open(os.path.join(REPO, "tools", "tb_realfile.v"),
               encoding="utf-8", errors="surrogateescape").read()
tb = base
tb = re.sub(r"parameter MAXB\s*=\s*\d+;", "parameter MAXB         = %d;" % MAXB, tb)
tb = re.sub(r"parameter NPKT\s*=\s*\d+;", "parameter NPKT         = %d;" % pkts, tb)
tb = re.sub(r"parameter EXP_MESSAGES\s*=\s*\d+;",
            "parameter EXP_MESSAGES = %d;" % msgs, tb)
tb = re.sub(r"parameter TOTAL_BYTES\s*=\s*\d+;",
            "parameter TOTAL_BYTES  = %d;" % nbytes, tb)
tb = re.sub(r"repeat \(\d+\) @\(negedge aclk\);\s*\n\s*\$display\(\"REALFILE",
            "repeat (%d) @(negedge aclk);\n    $display(\"REALFILE" % POST, tb)
tbpath = os.path.join(WORK, "tb_realfile_gen.v")
io.open(tbpath, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(tb)

os.environ["PATH"] = r"D:\Xilinx\Vivado\2024.1\bin;" + os.environ.get("PATH", "")


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


r = run([XVLOG, os.path.join(REPO, "rtl", "itch", "mold64_reasm.v"), tbpath], WORK)
if "ERROR" in r.stdout:
    print(r.stdout[-2000:])
    sys.exit(1)

r = run([XELAB, "-debug", "typical", "tb_realfile", "-s", "tb_realfile"], WORK)
if "ERROR" in r.stdout:
    print(r.stdout[-2000:])
    sys.exit(1)

print("running simulation (this takes a while for the large capture)...")
r = run([XSIM, "tb_realfile", "-runall"], WORK)
for line in r.stdout.splitlines():
    if line.strip().startswith(("SCAN", "REALFILE", "ERRSITES", "FIRSTERR")):
        print(line.strip())
