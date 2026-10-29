"""Find what makes mold64_reasm fail at a 128-cycle stall but not 96.

Measured threshold (tools/sweep_stall.py):

    stall  8..96   -> 1226916 bytes, 0 mismatches, 850 packets, gap=0  PASS
    stall 128..200 -> 1196274 bytes, 1013272 mismatches, 325 packets, gap=7 FAIL

A hard cliff at 2^7, with FIFO_AW = 12, means the 128 is NOT a pointer width.
This script enumerates the design's 7-bit and power-of-two registers and any
counter that could saturate at 127, so the suspect is identified from the source
rather than guessed.
"""
import io
import re

SRC = r"D:\agent\nasdaq-fpga\rtl\itch\mold64_reasm.v"
src = io.open(SRC, encoding="utf-8", errors="surrogateescape").read()

print("reg declarations whose width could saturate at 127 or 255:")
for m in re.finditer(r"^\s*(?:reg|wire)\s*(\[[^\]]+\])?\s*(\w+)\s*;", src, re.M):
    width = m.group(1) or ""
    name = m.group(2)
    if not width:
        continue
    print("  %-22s %s" % (name, width))

print()
print("localparams / parameters equal to a power of two:")
for m in re.finditer(r"^\s*(?:localparam|parameter)[^=]*=\s*([0-9]+)", src, re.M):
    v = int(m.group(1))
    if v and (v & (v - 1)) == 0:
        line = src[:m.start()].count("\n") + 1
        txt = src.splitlines()[line - 1].strip()
        print("  line %-5d %s" % (line, txt[:100]))

print()
print("timeout / max counters and their compares:")
for m in re.finditer(r"(\w*(?:MAX|TIMEOUT|LIMIT|DEPTH|CNT_MAX|THRESH)\w*)", src):
    name = m.group(1)
    line = src[:m.start()].count("\n") + 1
    txt = src.splitlines()[line - 1].strip()
    if "//" in txt:
        txt = txt.split("//")[0].strip()
    print("  line %-5d %-22s %s" % (line, name, txt[:80]))
