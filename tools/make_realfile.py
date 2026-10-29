"""Emit the capture file as a $readmemh image for tb_realfile.v."""
import io
import os

# The source may be overridden so an experiment can drive a modified capture through the
# testbench. Without REALFILE_SRC this is the normal capture.
SRC = (os.environ.get("REALFILE_SRC")
       or r"D:\agent\nasdaq-fpga\data\itch_loc6836.mold64")
OUT = os.path.join(os.environ["TEMP"], "nasdaq_rf", "img.hex")

os.makedirs(os.path.dirname(OUT), exist_ok=True)

with open(SRC, "rb") as f:
    data = f.read()

# $readmemh wants one hex value per line, matching the 8-bit array element.
with io.open(OUT, "w", encoding="ascii", newline="\n") as f:
    for byte in data:
        f.write("%02x\n" % byte)

print("wrote %s" % OUT)
print("bytes: %d" % len(data))
