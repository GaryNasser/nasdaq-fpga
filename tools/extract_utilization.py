"""Extract device utilisation from the routed report, and compare to the docs.

The assignment promises to report LUT/FF/BRAM/DSP. The report states:

    LUT 4,116 (7.74%)   FF 5,146 (4.84%)   BRAM 14 (10%)   DSP 0

The routed report from today's build says:

    LUT as Logic     3964
    LUT as Memory     543     -> total 4507
    Register as FF   5372
    Block RAM Tile     14
    DSPs                0

So LUT is understated by 391 (+9.5%) and FF by 226 (+4.4%). The documented figures
predate the byte-FIFO rewrite, which added the write-alignment stage and its hold
registers.

BRAM and DSP match. This prints the authoritative numbers so the document can be
corrected from data rather than retyped, and so a future build is checked against
them instead of drifting again.
"""
import io
import re

RPT = (r"D:\agent\nasdaq-fpga\vivado\workspace\nasdaq\nasdaq.runs\impl_1"
       r"\nasdaq_wrapper_utilization_placed.rpt")

text = io.open(RPT, encoding="utf-8", errors="replace").read()


def grab(pattern, cast=int):
    m = re.search(pattern, text)
    return cast(m.group(1)) if m else None


lut_logic = grab(r"\|\s+LUT as Logic\s+\|\s+(\d+)")
lut_mem = grab(r"\|\s+LUT as Memory\s+\|\s+(\d+)")
ff = grab(r"\|\s+Register as Flip Flop\s+\|\s+(\d+)")
latch = grab(r"\|\s+Register as Latch\s+\|\s+(\d+)")
bram = grab(r"\|\s+Block RAM Tile\s+\|\s+(\d+)")
dsp = grab(r"\|\s+DSPs\s+\|\s+(\d+)")
mmcm = grab(r"\|\s+MMCME2_ADV\s+\|\s+(\d+)")

CAP = {"LUT": 53200, "FF": 106400, "BRAM": 140, "DSP": 220, "MMCM": 4}

lut_total = (lut_logic or 0) + (lut_mem or 0)

rows = [
    ("LUT", lut_total, CAP["LUT"]),
    ("FF", ff or 0, CAP["FF"]),
    ("BRAM", bram or 0, CAP["BRAM"]),
    ("DSP", dsp or 0, CAP["DSP"]),
    ("MMCM", mmcm or 0, CAP["MMCM"]),
]

lines = []
lines.append("device utilisation from the routed report")
lines.append("  %s" % RPT.split("\\")[-1])
lines.append("")
lines.append("| resource | used | available | util |")
lines.append("| --- | --- | --- | --- |")
for name, used, cap in rows:
    lines.append("| %s | %d | %d | %.2f%% |"
                 % (name, used, cap, 100.0 * used / cap if cap else 0))

lines.append("")
lines.append("LUT breakdown: %d logic + %d memory (440 distributed RAM + 103 shift reg)"
             % (lut_logic or 0, lut_mem or 0))
lines.append("Latches: %s" % (latch if latch is not None else "?"))

# Compare against what the report currently claims.
DOC = r"D:\agent\nasdaq-fpga\docs\final-report.md"
doc = io.open(DOC, encoding="utf-8").read()
doc_lut = re.search(r"LUT \| \*\*([\d,]+)\*\*", doc)
doc_ff = re.search(r"FF \| \*\*([\d,]+)\*\*", doc)
lines.append("")
lines.append("documented vs actual")
for label, m, actual in (("LUT", doc_lut, lut_total), ("FF", doc_ff, ff)):
    if m:
        dv = int(m.group(1).replace(",", ""))
        lines.append("  %-4s doc %-6d actual %-6d diff %+d" % (label, dv, actual, actual - dv))

out = io.open(r"C:\Users\qingx\AppData\Local\Temp\util.txt", "w", encoding="utf-8")
out.write("\n".join(lines))
out.close()

for line in lines:
    if line.isascii():
        print(line)
