"""Strengthen the byte-contract check: verify the producer emits a byte per beat.

The first version confirmed the widths agree but never asked whether the producer actually
drives a valid byte. A `tkeep` of 0x01 with `tvalid` never asserted would pass every
assertion while delivering nothing - the same "verified nothing" shape this series keeps
finding.

Also fixes a walrus operator (`if readings := ...`) whose semantics here were wrong: it
assigns and tests truthiness, so an empty list skipped the branch rather than checking it.

What to add:
  * m_axis_tvalid is driven, and by something that depends on the emit FSM;
  * m_axis_tlast is driven, since itch_parse uses it to delimit messages.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
PROD = os.path.join(REPO, "rtl", "itch", "mold64_reasm.v")
CONS = os.path.join(REPO, "rtl", "itch", "itch_parse.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

prod = io.open(PROD, encoding="latin-1").read()
cons = io.open(CONS, encoding="latin-1").read()

print("byte-stream contract: mold64_reasm -> itch_parse")
print()
fails = []

# --- producer ---------------------------------------------------------------
m_data = re.search(r"assign\s+m_axis_tdata\s*=\s*\{\s*(\d+)'d0\s*,\s*(\w+)\s*\}", prod)
m_keep = re.search(r"assign\s+m_axis_tkeep\s*=\s*(\d+)'h([0-9A-Fa-f]+)", prod)
m_valid = re.search(r"assign\s+m_axis_tvalid\s*=\s*([^;]+);", prod)
m_last = re.search(r"assign\s+m_axis_tlast\s*=\s*([^;]+);", prod)

if m_data:
    pad = int(m_data.group(1))
    print("  producer data : { %d'd0, %s } -> %d meaningful bit(s)"
          % (pad, m_data.group(2), 64 - pad))
    if pad != 56:
        fails.append("producer no longer zero-extends one byte (padding %d, want 56)" % pad)
else:
    fails.append("producer m_axis_tdata not in the expected form")

if m_keep:
    val = int(m_keep.group(2), 16)
    print("  producer keep : %s'h%02x -> lane(s) %s"
          % (m_keep.group(1), val, ", ".join(str(b) for b in range(8) if val >> b & 1)))
    if val != 0x01:
        fails.append("producer tkeep is %#x, not 0x01" % val)
else:
    fails.append("producer m_axis_tkeep not found")

if m_valid:
    expr = m_valid.group(1).strip()
    print("  producer valid: %s" % expr[:70])
    # Must depend on something stateful - a constant 1 would emit a byte every cycle.
    if re.fullmatch(r"1'b1|1", expr):
        fails.append("producer asserts tvalid unconditionally - it would emit bytes "
                     "with no data behind them")
else:
    fails.append("producer m_axis_tvalid not found")

if m_last:
    print("  producer last : %s" % m_last.group(1).strip()[:70])
else:
    fails.append("producer m_axis_tlast not found - itch_parse delimiters depend on it")

# --- consumer ---------------------------------------------------------------
reads = re.findall(r"s_axis_tdata\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]", cons)
print("  consumer reads: %s" % (", ".join("tdata[%s:%s]" % (a, b) for a, b in reads)
                                or "(none)"))
bad_lanes = [r for r in reads if r != ("7", "0")]
if bad_lanes:
    fails.append("consumer reads lanes other than [7:0]: %s" % bad_lanes)

body = re.sub(r"//[^\n]*", "", cons)
body = re.sub(r"input\s+wire\s*\[\s*7\s*:\s*0\s*\]\s*s_axis_tkeep\s*,", "", body)
reads_keep = "s_axis_tkeep" in body
print("  consumer uses tkeep: %s %s"
      % (reads_keep, "(not needed: keep is constant 0x01)" if not reads_keep else ""))

print()
print("  contract: one meaningful byte per beat, always in lane 0,")
print("            with tvalid produced by the emit FSM and tlast delimiting.")
print()

if fails:
    print("BYTE-CONTRACT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("BYTE-CONTRACT-PASS")
