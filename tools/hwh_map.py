"""Map each IP to its real AXI-Lite base address from the handoff.

mock_run.py invented addresses (0x40410000...). find_ip() matches on the ip_dict
KEY rather than the address, so the driver's logic was exercised correctly either
way - but a mock with fictional addresses cannot expose address aliasing and
misleads a reader comparing it to hardware.

The hwh carries the mapping in <MEMRANGE ... INSTANCE="x_0" BASEVALUE="0x...">.
This extracts it and compares against what the mock uses.
"""
import io
import re

HWH = r"D:\agent\nasdaq-fpga\vivado/out\nasdaq.hwh"
MOCK = r"D:\agent\nasdaq-fpga\tools\mock_run.py"

hwh = io.open(HWH, "rb").read().decode("latin-1")

print("MEMRANGE entries in the shipped handoff")
real = {}
for m in re.finditer(r"<MEMRANGE ([^>]*)/>", hwh):
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    inst = attrs.get("INSTANCE")
    base = attrs.get("BASEVALUE")
    high = attrs.get("HIGHVALUE")
    mt = attrs.get("MEMTYPE")
    if inst and base:
        print("  %-16s %-12s %-10s %s" % (inst, base, mt, high))
        if mt == "REGISTER" or (mt not in real):
            real.setdefault(inst, base)

print()
print("mock addresses")
mock = io.open(MOCK, encoding="utf-8", errors="surrogateescape").read()
stub = re.findall(r"'(\w+_0)':\s*\{\s*'phys_addr':\s*(0x[0-9A-Fa-f]+)", mock)
for name, addr in stub:
    print("  %-16s %s" % (name, addr))

print()
print("comparison")
for name, addr in stub:
    r = real.get(name)
    same = (r is not None and int(r, 16) == int(addr, 16))
    print("  %-16s mock=%s real=%s %s"
          % (name, addr, r or "(none)", "SAME" if same else "DIFFERENT"))

if real:
    print()
    print("real AXI-Lite register bases (MEMTYPE=REGISTER):")
    for n, a in real.items():
        print("  %-16s %s" % (n, a))
