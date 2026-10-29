"""Two documents described the pre-rewrite design as current. Keep them describing the shipped one.

    mold64_reasm.v header   said "TLAST = packet last beat", the single-packet design
    bringup-defects.md      said the byte-FIFO rewrite was "reverted - not shipped"

Both were written when true and never revisited. The shipped RTL says:

    wire s_can_write = enable && fifo_has_room;
    assign s_axis_tready = s_can_write;

so TREADY does not depend on packet boundaries at all.

The property to keep: the module header must not describe the TLAST-per-packet behaviour as
current, and the log must not say the rewrite is unshipped without a status update.

Testing by content, because these are documents. A reader trusting the header would assume the
3-packet overflow still exists.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch", "mold64_reasm.v")
LOG = os.path.join(REPO, "docs", "bringup-defects.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

rtl = io.open(RTL, encoding="latin-1").read()
log = io.open(LOG, encoding="utf-8", errors="surrogateescape").read()

print("the shipped RTL's flow control")
print()

fails = []

# 1. TREADY must not depend on packet boundaries in the shipped logic.
# Comments describe the OLD design; strip them before reading the logic.
code = re.sub(r"//[^\n]*", "", rtl)
m = re.search(r"wire s_can_write\s*=\s*([^;]+);", code)
if not m:
    fails.append("s_can_write not found - the flow control changed shape")
    print("  s_can_write            NOT FOUND")
else:
    expr = m.group(1).strip()
    depends_on_packet = bool(re.search(r"pkt_rx_done|pkt_hold|s_pkt_last", expr))
    print("  s_can_write            %s" % expr[:60])
    print("  depends on packet end  %s" % depends_on_packet)
    if depends_on_packet:
        fails.append("TREADY depends on a packet boundary again")

# 2. The header must state the current behaviour.
head = rtl[:3000]
m2 = re.search(r"//\s*Input\s*:((?:[^\n]*\n//[^\n]*){0,10})", head)
header_text = m2.group(0) if m2 else ""
mentions_fifo_room = "fifo_has_room" in header_text
says_tlast_packet = bool(re.search(r"TLAST = packet\s*\n//\s*last beat", header_text))
print("  header cites fifo_has_room   %s" % mentions_fifo_room)
print("  header still says TLAST=pkt %s" % says_tlast_packet)
if not mentions_fifo_room:
    fails.append("the module header does not describe the byte-FIFO flow control")
if says_tlast_packet:
    fails.append("the module header still asserts TLAST-per-packet buffering")

# 3. The log must not leave "reverted - not shipped" unqualified.
i = log.find("Partial attempt")
if i >= 0:
    window = log[i:i + 900]
    has_update = "IS shipped" in window or "was subsequently completed" in window
    print("  log entry carries a status    %s" % has_update)
    if not has_update:
        fails.append("the log still says the rewrite is unshipped, with no update")

print()
if fails:
    print("FIFO-DOC-FAIL (%d)" % len(fails))
    for f in fails:
        print("  %s" % f)
    sys.exit(1)
print("FIFO-DOC-PASS (the RTL, its header and the bring-up log agree on the shipped design)")
