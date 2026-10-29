"""Run board/load_overlay.py against a simulated overlay, with no board.

The driver has never executed against this bitstream. Every register offset,
control sequence and return-code path in it is unverified; errors there surface
on hardware as an unexplained wrong read, after a power cycle nobody can
currently perform.

This stubs the small PYNQ surface the driver uses (pynq.Overlay, pynq.MMIO,
pynq.allocate, ol.ip_dict, dma.sendchannel) with a register model that mirrors
the RTL's documented behaviour, then runs the REAL driver code against it in a
subprocess and checks the exit code and output.

Register model, taken from the RTL:
  * mold64_reasm  0x00..0x18 : rx_packets/messages, gap, err, CTRL
  * itch_parse    0x00..0x14 : parse_cnt/..., CTRL
  * order_book    0x00..0x30 : counters..., CTRL (bit0 enable only)
  * ts_hist       0x00..0x478: CTRL(bit0 enable, bit1 clear), min/max/sum/
                               count, 256 histogram bins at 0x30
Counters are produced when the driver writes the enables, so a missing or wrong
enable shows up as GOLDEN-SKIPPED or FAIL rather than silently passing.

What this catches: wrong offsets, missing enables, bad return codes, crashes.
What it cannot catch: anything requiring real hardware timing.
"""
import io
import os
import shutil
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
DRIVER = os.path.join(REPO, "board", "load_overlay.py")
DATA = os.path.join(REPO, "data", "itch_loc6836.mold64")
WORK = os.path.join(os.environ["TEMP"], "nasdaq_mockrun")

GOLD = dict(add_cnt=15334, exe_cnt=7, can_cnt=12518, del_cnt=15291,
            rep_cnt=238, drop_cnt=12826, order_cnt=320, level_cnt=95)

STUB = '''"""Minimal PYNQ stand-in with an RTL-faithful register model."""
import numpy as np

COUNT = 43428
PACKETS = 850

GOLD = dict(add_cnt=15334, exe_cnt=7, can_cnt=12518, del_cnt=15291,
            rep_cnt=238, drop_cnt=12826, order_cnt=320, level_cnt=95)


class MMIO:
    _reset_hazard = False
    def __init__(self, base, length):
        self.base = int(base)
        self.length = length
        self.mem = MMIO._mem.setdefault(self.base, {})

    _mem = {}

    def write(self, offset, value):
        self.mem[int(offset)] = int(value)
        MMIO._on_write(self.base, int(offset), int(value))

    def read(self, offset):
        MMIO._on_read(self.base, int(offset))
        return int(self.mem.get(int(offset), 0))

    # --- which module is this? keyed off the stub's base addresses ----------
    @staticmethod
    def _which(base):
        return {0x40010000: 'dma', 0x40001000: 'm64', 0x40000000: 'ip',
                0x40002000: 'book', 0x40003000: 'ts'}.get(base)

    @staticmethod
    def _mem_of(base):
        return MMIO._mem.setdefault(base, {})

    @staticmethod
    def _on_write(base, off, val):
        which = MMIO._which(base)
        m = MMIO._mem_of(base)
        if which == 'm64' and off == 0x18:
            en = val & 1
            rst = (val >> 1) & 1
            # A reset written in the SAME transaction as enable, with the transfer
            # starting immediately, destroys the word inside the registered commit
            # stage: measured on hardware as 849/850 packets and in simulation
            # (tools/tb_reset_seq.v) as pkts=0, err=39. Model that by remembering
            # the ordering hazard until another CTRL write clears it.
            MMIO._reset_hazard = bool(rst and en)
            m[0x00] = PACKETS if en else 0
            m[0x04] = 0
            m[0x08] = COUNT if en else 0
            m[0x0C] = 0
            m[0x10] = 0
            m[0x14] = 0
        elif which == 'ip' and off == 0x14:
            en = val & 1
            m[0x00] = COUNT if en else 0
            m[0x04] = 0
            m[0x08] = 0
            m[0x0C] = 0
            m[0x10] = 0
        elif which == 'book' and off == 0x30:
            en = val & 1
            # order_book has NO soft reset: counters persist once enabled.
            if en and m.get(0x18, 0) == 0:
                m[0x18] = GOLD['add_cnt']
                m[0x1C] = GOLD['exe_cnt']
                m[0x20] = GOLD['can_cnt']
                m[0x24] = GOLD['del_cnt']
                m[0x28] = GOLD['rep_cnt']
                m[0x2C] = GOLD['drop_cnt']
                m[0x00] = GOLD['order_cnt']
                m[0x04] = GOLD['level_cnt']
        elif which == 'ts' and off == 0x00 and (val & 1):
            m[0x18] = 2            # min cycles
            m[0x1C] = 735          # max cycles
            m[0x20] = 1124144 & 0xFFFFFFFF
            m[0x24] = 0
            m[0x28] = 19969
            m[0x2C] = 0
            m[0x30] = 613          # histogram bins
            m[0x34] = 4613
            m[0x3C] = 1224
            m[0x40] = 1779
            m[0x44] = 1749
        elif which == 'ts' and off == 0x478:
            m[0x478] = 1000

    @staticmethod
    def _on_read(base, off):
        which = MMIO._which(base)
        m = MMIO._mem_of(base)
        if which == 'ts' and off == 0x478:
            m[0x478] = m.get(0x478, 0) + 250000


class _Channel:
    def transfer(self, buf):
        pass

    def wait(self):
        pass


class _DMA:
    def __init__(self):
        self.sendchannel = _Channel()


class Overlay:
    def __init__(self, bitfile=None, ignore_version=False):
        self.bitfile_name = bitfile
        # REAL AXI-Lite bases from the shipped nasdaq.hwh (MEMTYPE=REGISTER):
        #   itch_parse_0    0x40000000
        #   mold64_reasm_0  0x40001000
        #   order_book_0    0x40002000
        #   ts_hist_0       0x40003000
        #   axi_dma_0       0x40010000
        # Using the real values rather than invented ones means the mock can
        # expose address aliasing, and a reader comparing it to hardware is not
        # misled. (The earlier invented 0x404x0000 values all worked anyway,
        # because find_ip() matches the dict KEY, not the address.)
        self.ip_dict = {
            'itch_parse_0':   {'phys_addr': 0x40000000},
            'mold64_reasm_0': {'phys_addr': 0x40001000},
            'order_book_0':   {'phys_addr': 0x40002000},
            'ts_hist_0':      {'phys_addr': 0x40003000},
            'axi_dma_0':      {'phys_addr': 0x40010000},
        }
        self.axi_dma_0 = _DMA()

    def download(self):
        pass


def allocate(shape=0, dtype='u1'):
    return np.zeros(shape, dtype=np.uint8)
'''

os.makedirs(WORK, exist_ok=True)
NUMPY_SRC = '''"""Tiny numpy stand-in: only what load_overlay.py needs."""
import array

uint8 = 'B'


class _Arr(array.array):
    def __new__(cls, n):
        return super().__new__(cls, 'B', bytes(int(n)))

    def flush(self):
        pass

    def freebuffer(self):
        pass

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            data = bytes(value)
            start = key.start or 0
            for i, b in enumerate(data):
                array.array.__setitem__(self, start + i, b)
        else:
            array.array.__setitem__(self, key, value)


def zeros(shape, dtype=None):
    return _Arr(shape)


def frombuffer(buf, dtype=None):
    return array.array('B', bytes(buf))
'''

io.open(os.path.join(WORK, "numpy.py"), "w", encoding="utf-8",
        newline="\n").write(NUMPY_SRC)
io.open(os.path.join(WORK, "pynq.py"), "w", encoding="utf-8",
        newline="\n").write(STUB)
shutil.copy(DRIVER, os.path.join(WORK, "load_overlay.py"))
shutil.copy(DATA, os.path.join(WORK, "itch_loc6836.mold64"))

env = dict(os.environ)
env["PYTHONPATH"] = WORK

CASES = [
    ("--book --input itch_loc6836.mold64 --repeat 1", 0, "GOLDEN-OK"),
    ("--book --input itch_loc6836.mold64 --repeat 4", 0, "GOLDEN-SKIPPED"),
    ("--book --input itch_loc6836.mold64 --repeat 1 --no-golden", 0, "GOLDEN-SKIPPED"),
    ("--book", 2, "FAIL-ARGS"),
    ("--pipeline --input itch_loc6836.mold64 --messages 43428", 0, "PIPELINE-OK"),
    ("--pipeline --input itch_loc6836.mold64", 2, "FAIL-ARGS"),
    ("--loopback --pipeline", 2, "FAIL-ARGS"),
]

if __name__ == '__main__':
    fails = []
    print("running the real driver against the simulated overlay")
    print()
    for args, want_rc, want_text in CASES:
        r = subprocess.run([sys.executable, "load_overlay.py"] + args.split(),
                           cwd=WORK, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        rc = r.returncode
        out = r.stdout + r.stderr
        ok_rc = (rc == want_rc)
        ok_txt = (want_text in out)
        status = "OK " if (ok_rc and ok_txt) else "FAIL"
        print("[%s] %-58s rc=%d want %d  %s" %
              (status, args, rc, want_rc, "found " + want_text if ok_txt else "MISSING " + want_text))
        if not (ok_rc and ok_txt):
            fails.append(args)
            tail = "\n".join(out.strip().splitlines()[-8:])
            print("      --- output tail ---")
            for line in tail.splitlines():
                print("      " + line)

    print()
    if fails:
        print("MOCK-RUN-FAIL (%d of %d cases)" % (len(fails), len(CASES)))
        for f in fails:
            print("  " + f)
        sys.exit(1)
    print("MOCK-RUN-PASS (%d cases)" % len(CASES))
