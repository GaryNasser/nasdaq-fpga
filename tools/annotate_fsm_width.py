"""Annotate order_book's state register with its remaining headroom.

`reg [3:0] state` holds 16 encodings and the FSM uses 15 (ST_IDLE=0 .. ST_MAP_CMP=14).
Exactly one remains. Nothing in the source says so: the constraint emerges from a
register width in one place and a list of localparams in another, and a 17th state
would write 4'd16, truncate to 4'd0 = ST_IDLE, and re-enter idle silently.

A comment at the declaration is the cheapest defence, because the person adding a
state edits that region. tools/check_fsm_width.py is the enforcing one.
"""
import io

PATH = r"D:\agent\nasdaq-fpga\rtl\itch\order_book.v"
text = io.open(PATH, encoding="utf-8", errors="surrogateescape").read()

old = "  reg [3:0] state;"
new = """  // NOTE: 4 bits = 16 encodings; 15 are used (ST_IDLE=0 .. ST_MAP_CMP=14), so
  // exactly ONE remains. A 17th state would be written as 4'd16, truncate to
  // 4'd0 = ST_IDLE and silently re-enter idle. Widen to [4:0] before adding a
  // second one. mold64_reasm already went through this: its state widened from
  // 4 to 5 bits when the byte-FIFO rewrite pushed past 16 states.
  // Enforced by tools/check_fsm_width.py.
  reg [3:0] state;"""

if "exactly ONE remains" in text:
    print("annotation already present")
else:
    assert old in text, "state declaration not found"
    text = text.replace(old, new, 1)
    io.open(PATH, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(text)
    print("annotation added")
