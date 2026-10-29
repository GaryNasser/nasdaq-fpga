"""Check that every declared FSM state is both entered and handled.

Round 82 found order_book has one spare encoding. That count only matters if the
15 declared states are all live - a state that is declared but never targeted, or
targeted but has no case arm, is either dead weight or a silent no-op.

Three things to establish per state:
  1. a `localparam ST_X` declaration exists;
  2. it is assigned somewhere (state <= ST_X) or used as a goto target;
  3. it has a `ST_X:` case arm that does something.

A state that is targeted but has no arm would fall through the case statement and
leave `state` unchanged - the FSM would hang in it forever. That is a much worse
defect than a wasted encoding, and it is invisible to a compile.
"""
import io
import re
import sys

MODULES = [
    ("mold64_reasm", r"D:\agent\nasdaq-fpga\rtl\itch\mold64_reasm.v"),
    ("order_book", r"D:\agent\nasdaq-fpga\rtl\itch\order_book.v"),
]

report = []
fails = []

report.append("FSM state liveness")
report.append("=" * 70)

for name, path in MODULES:
    src = io.open(path, encoding="utf-8", errors="surrogateescape").read()

    declared = {}
    for m in re.finditer(r"localparam\s*\[\d+:0\]\s*(ST_\w+)\s*=\s*(\d+)'d(\d+)", src):
        declared[m.group(1)] = int(m.group(3))

    if not declared:
        report.append("%-14s no ST_ localparams" % name)
        continue

    report.append("%-14s %d declared states" % (name, len(declared)))

    # Targets: any `state <= ST_X` or `<= ST_X;`
    targets = set(re.findall(r"state\s*<=\s*(ST_\w+)", src))
    # Case arms: `ST_X: begin` or `ST_X:` at line start (indented)
    arms = set(re.findall(r"^\s*(ST_\w+)\s*:", src, re.M))

    for sname, val in sorted(declared.items(), key=lambda kv: kv[1]):
        is_idle = (sname == "ST_IDLE")
        entered = sname in targets or is_idle
        handled = sname in arms
        flags = []
        if not entered:
            flags.append("NEVER ENTERED")
        if not handled:
            flags.append("NO CASE ARM")
        status = "OK" if not flags else " / ".join(flags)
        if flags:
            fails.append("%s: %s %s" % (name, sname, status))
        report.append("%-14s   %-16s = %2d  %s" % ("", sname, val, status))

    # Reverse check: an arm for an undeclared state.
    for a in sorted(arms):
        if a not in declared:
            report.append("%-14s   %-16s arm but NOT DECLARED" % ("", a))
            fails.append("%s: case arm for undeclared %s" % (name, a))
    report.append("")

report.append("=" * 70)
out = io.open(r"C:\Users\qingx\AppData\Local\Temp\fsmlive.txt", "w", encoding="utf-8")
out.write("\n".join(report))
out.write("\n\n")
out.write("FSM-LIVENESS-FAIL (%d)\n" % len(fails) if fails else "FSM-LIVENESS-PASS\n")
out.close()

for line in report:
    if line.isascii():
        print(line)
for f in fails:
    print("  " + f)
print("FSM-LIVENESS-FAIL (%d)" % len(fails) if fails else "FSM-LIVENESS-PASS")
sys.exit(1 if fails else 0)
