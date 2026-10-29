import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(REPO, 'vivado', 'out', 'nasdaq.hwh')
h = open(path, 'rb').read().decode('utf-8', 'replace')

ports = ['S00_ARESETN', 'M00_ARESETN', 'ARESETN', 'S00_ACLK', 'M00_ACLK',
         'S00_AXI_araddr', 'M00_AXI_araddr']

for port in ports:
    # "INSTANCE=axi_mem_intercon PORT=<port>"  (a connection whose peer is the intercon)
    pat = 'INSTANCE="axi_mem_intercon" PORT="%s"' % port
    n = len(re.findall(re.escape(pat), h))
    print('%-16s connections mentioning it: %d' % (port, n))

print()
# All PORT blocks owned by axi_mem_intercon: find its MODULE region and list names.
i = h.find('<MODULE FULLNAME="axi_mem_intercon"')
if i < 0:
    i = h.find('FULLNAME="axi_mem_intercon"')
print('module idx', i)
if i > 0:
    seg = h[i:i + 60000]
    names = re.findall(r'<PORT[^>]*NAME="([^"]+)"', seg)
    print('axi_mem_intercon ports:', sorted(set(names)))
