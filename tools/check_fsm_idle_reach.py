"""Count Verilog block depth correctly.

The previous attempt accumulated `body.count("begin") - body.count("end")`, which is wrong
twice over:

  * `end` matches inside `endcase`, `endmodule`, `endfunction` - each counted as a block end
    when it is not one;
  * `begin`/`end` inside a comment or a string would count too.

Result: the brace depth never returned to 0 after ST_IDLE's body, so every later `ST_X:`
looked nested and only one arm was recorded.

Correct approach: tokenise on whole words. Depth goes up on `begin` and down on `end`
only, with `endcase`, `endmodule`, `endfunction`, `endtask`, `endgenerate` excluded by
using word boundaries and an explicit exclusion set.

Python's `\\b` handles the boundaries: `\\bend\\b` does not match `endcase` because `c`
follows `d` and there is no word boundary there.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
OB = os.path.join(REPO, "rtl", "itch", "order_book.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(OB, encoding="latin-1").read()

# Strip comments so their text cannot affect depth.
code = re.sub(r"//[^\n]*", "", src)
code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)

m = re.search(r"case\s*\(\s*state\s*\)", code)
if not m:
    print("case(state) not found")
    sys.exit(1)

# Find the matching endcase.
depth = 1
i = m.end()
body_start = i
body = None
while i < len(code):
    nxt_case = re.compile(r"\bcase\b").search(code, i)
    nxt_end = re.compile(r"\bendcase\b").search(code, i)
    if nxt_end is None:
        break
    if nxt_case is not None and nxt_case.start() < nxt_end.start():
        depth += 1
        i = nxt_case.end()
    else:
        depth -= 1
        if depth == 0:
            body = code[body_start:nxt_end.start()]
            break
        i = nxt_end.end()

if body is None:
    print("unbalanced case/endcase")
    sys.exit(1)

# Walk the body tracking begin/end depth, recording ST_X: labels at depth 0.
TOKEN = re.compile(r"\b(begin|end|ST_[A-Z_]+)\b\s*:?")
depths = []
d = 0
for tm in TOKEN.finditer(body):
    tok = tm.group(1)
    if tok == "begin":
        d += 1
    elif tok == "end":
        d = max(0, d - 1)
    else:
        depths.append((tm.start(), tok, d))

top = [(pos, name) for pos, name, dd in depths if dd == 0]
print("order_book FSM")
print()
print("  ST_ labels found        : %d" % len(depths))
print("  at begin/end depth 0    : %d" % len(top))
print("  %s" % ", ".join(n for _, n in top))
print()

arms = {}
for k, (pos, name) in enumerate(top):
    end = top[k + 1][0] if k + 1 < len(top) else len(body)
    arms[name] = body[pos:end]

graph = {}
for name, chunk in arms.items():
    graph[name] = set(re.findall(r"state\s*<=\s*(ST_[A-Z_]+)", chunk))

can_reach = {"ST_IDLE"}
changed = True
while changed:
    changed = False
    for s, succ in graph.items():
        if s not in can_reach and (succ & can_reach):
            can_reach.add(s)
            changed = True

print("  states reaching ST_IDLE : %d of %d" % (len(can_reach), len(graph)))
print()
stuck = []
for s in sorted(graph):
    succ = sorted(graph[s])
    ok = s in can_reach
    if not ok:
        stuck.append(s)
    print("  %-16s -> %s %s"
          % (s, ",".join(succ) if succ else "(none)", "" if ok else "STUCK"))

print()
if len(top) < 5:
    print("FSM-IDLE-REACH-FAIL (only %d top-level states parsed; the graph is incomplete)"
          % len(top))
    sys.exit(1)
if stuck:
    print("FSM-IDLE-REACH-FAIL (%d)" % len(stuck))
    for s in stuck:
        print("  %s cannot reach ST_IDLE" % s)
    sys.exit(1)
print("FSM-IDLE-REACH-PASS")
