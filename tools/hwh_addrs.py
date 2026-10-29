"""Extract the real AXI-Lite base addresses from the shipped handoff.

mock_run.py uses invented base addresses (0x40410000 ...). find_ip() matches on
the ip_dict KEY, not the address, so any distinct values work for the driver's
logic - but knowing the real ones matters for two reasons:

  * a reader comparing the mock to hardware should see what hardware returns;
  * if a real base address ever collided with a module boundary, the mock could
    hide an aliasing bug the silicon would exhibit.

This prints them from the hwh without assuming a format.
"""
import io
import re

HWH = r"D:\agent\nasdaq-fpga\vivado/out\nasdaq.hwh"
hwh = io.open(HWH, "rb").read().decode("latin-1")

print("all BASEVALUE entries:")
for m in re.finditer(r'BASEVALUE="([^"]+)"', hwh):
    print("  %s" % m.group(1))

print()
print("all distinct BASEADDR entries (first 12):")
seen = []
for m in re.finditer(r'BASEADDR="([^"]+)"', hwh):
    v = m.group(1)
    if v not in seen:
        seen.append(v)
for v in seen[:12]:
    print("  %s" % v)
print("  ... %d distinct total" % len(seen))

print()
print("address-bearing elements near each IP instance:")
for ip in ("mold64_reasm_0", "itch_parse_0", "order_book_0", "ts_hist_0",
           "axi_dma_0"):
    idx = hwh.find('NAME="%s"' % ip)
    if idx < 0:
        idx = hwh.find(ip)
    if idx < 0:
        print("  %-16s (not found)" % ip)
        continue
    window = hwh[max(0, idx - 1500): idx + 3000]
    vals = re.findall(r'(?:BASEVALUE|BASEADDR)="([^"]+)"', window)
    print("  %-16s %s" % (ip, sorted(set(vals))[:6] or "(none nearby)"))
