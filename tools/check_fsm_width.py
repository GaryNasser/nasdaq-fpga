"""Check that every FSM state encoding fits in its declared state register width.

`order_book.v` declares `reg [3:0] state` - 16 encodings - and uses 15 of them
(ST_IDLE=0 .. ST_MAP_CMP=14). One encoding remains. Nothing in the source states
this as a constraint; it is an emergent property of two numbers that live in
different places.

The hazard is real, not theoretical:

  * adding a 16th state needs 4'd15, the last legal value;
  * adding a 17th would write 4'd16, which truncates to 4'd0 = ST_IDLE, so the
    FSM would silently re-enter idle instead of the intended state;
  * simulation would show a wrong-but-plausible sequence, not a compile error;
  * Vivado emits a width-mismatch warning among thousands.

`mold64_reasm` already hit this class: its state widened from 4 to 5 bits when
the byte-FIFO rewrite pushed past 16 states (it now has 18, ST_EMIT_LEN_LO=17).

This checks each module's `ST_*` localparams against the width of its `state`
register, and reports remaining headroom so the next person sees the margin
before consuming it.
"""
import io
import re
import sys

MODULES = [
    ("mold64_reasm", r"D:\agent\nasdaq-fpga\rtl\itch\mold64_reasm.v"),
    ("itch_parse", r"D:\agent\nasdaq-fpga\rtl\itch\itch_parse.v"),
    ("order_book", r"D:\agent\nasdaq-fpga\rtl\itch\order_book.v"),
]

fails = []
report = []

report.append("FSM state-encoding headroom")
report.append("=" * 66)

for name, path in MODULES:
    src = io.open(path, encoding="utf-8", errors="surrogateescape").read()

    # Find the state register declaration.
    m = re.search(r"reg\s*\[(\d+):0\]\s*state\s*[;,]", src)
    if not m:
        m = re.search(r"reg\s*state\s*[;,]", src)
        if m:
            width = 1
        else:
            report.append("%-14s no `state` register found" % name)
            continue
    else:
        width = int(m.group(1)) + 1

    # Collect ST_ localparams: their declared literal width and value.
    states = []
    for sm in re.finditer(r"localparam\s*\[(\d+):0\]\s*(ST_\w+)\s*=\s*(\d+)'d(\d+)", src):
        decl_w = int(sm.group(1)) + 1
        val = int(sm.group(4))
        states.append((sm.group(2), val, decl_w))

    if not states:
        report.append("%-14s no ST_ localparams" % name)
        continue

    max_val = max(v for _, v, _ in states)
    capacity = 2 ** width

    # A declaration is not a used encoding. Count LIVE states: those that are
    # either a `state <=` target or have a case arm (plus ST_IDLE, which is
    # entered by the default arm and by reset). Round 82 counted declarations
    # and got headroom 1 for order_book; ST_DONE=10 is declared but dead, so the
    # true headroom is 2. That off-by-one is exactly what this check exists to
    # report correctly.
    targets = set(re.findall(r"state\s*<=\s*(ST_\w+)", src))
    arms = set(re.findall(r"^\s*(ST_\w+)\s*:", src, re.M))
    live = {n for n, _, _ in states if n in targets or n in arms or n == "ST_IDLE"}
    dead = {n for n, _, _ in states if n not in live}

    headroom = capacity - len(live)
    ok = max_val < capacity
    report.append("%-14s state width %d bits -> %d encodings" % (name, width, capacity))
    report.append("%-14s %d declared, %d live%s, max encoding %d"
                  % ("", len(states), len(live),
                     (", %d dead" % len(dead)) if dead else "", max_val))
    for d in sorted(dead):
        report.append("%-14s   dead state %s (declared, never targeted, no arm)"
                      % ("", d))
    report.append("%-14s free encodings: %d  %s"
                  % ("", headroom, "OK" if ok else "** OVERFLOW **"))

    # Every declaration's own literal width must also hold its value.
    for sname, val, decl_w in states:
        if val >= (2 ** decl_w):
            fails.append("%s: %s = %d' d%d does not fit its own %d-bit literal"
                         % (name, sname, decl_w, val, decl_w))
            report.append("%-14s   %s literal overflows" % ("", sname))
    if not ok:
        fails.append("%s: state encoding %d exceeds %d-bit register"
                     % (name, max_val, width))

    if headroom == 0:
        report.append("%-14s WARNING: register is exactly full - the next state added"
                      % "")
        report.append("%-14s will silently alias back to an existing encoding" % "")
    report.append("")

report.append("=" * 66)
report.append("note: order_book once had a dead state (ST_DONE, since removed);")
report.append("      mold64_reasm widened 4->5 bits - both prove this is a live hazard.")

out = io.open(r"C:\Users\qingx\AppData\Local\Temp\fsm.txt", "w", encoding="utf-8")
out.write("\n".join(report))
out.write("\n\n")
out.write("FSM-WIDTH-FAIL (%d)\n" % len(fails) if fails else "FSM-WIDTH-PASS\n")
out.close()

for line in report:
    if line.isascii():
        print(line)
for f in fails:
    print("  " + f)
print("FSM-WIDTH-FAIL (%d)" % len(fails) if fails else "FSM-WIDTH-PASS")
sys.exit(1 if fails else 0)
