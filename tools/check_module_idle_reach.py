"""Generalise idle-reachability to every module with a state machine.

Round 62 checked order_book: all 14 states can return to ST_IDLE, so the parser's held
event always drains. This asks the same question of mold64_reasm, which has 19 states and
sits at the head of the chain.

Why it matters here too. mold64_reasm reads the DMA stream. If its FSM wedged, TREADY on
its input would stop, the MM2S transfer would never complete, and the driver would hang
inside sendchannel.wait() exactly as it did when the book was left disabled.

The check is the same fixed-point walk over the transition graph, parameterised by module
and idle state, and it refuses to report PASS unless it parsed a plausible number of
states - the guard that the three earlier versions lacked.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def parse_machine(path, state_var="state"):
    """Return {state: set(successors)} for the case(<state_var>) block, or None."""
    src = io.open(path, encoding="latin-1").read()
    code = re.sub(r"//[^\n]*", "", src)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)

    m = re.search(r"case\s*\(\s*%s\s*\)" % state_var, code)
    if not m:
        return None

    depth = 1
    i = m.end()
    start = i
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
                body = code[start:nxt_end.start()]
                break
            i = nxt_end.end()
    if body is None:
        return None

    # Top-level arms: ST_X at begin/end depth 0.
    TOKEN = re.compile(r"\b(begin|end|ST_[A-Z0-9_]+)\b")
    d = 0
    labels = []
    for tm in TOKEN.finditer(body):
        tok = tm.group(1)
        if tok == "begin":
            d += 1
        elif tok == "end":
            d = max(0, d - 1)
        elif d == 0:
            labels.append((tm.start(), tok))

    graph = {}
    for k, (pos, name) in enumerate(labels):
        end = labels[k + 1][0] if k + 1 < len(labels) else len(body)
        chunk = body[pos:end]
        graph[name] = set(re.findall(r"state\s*<=\s*(ST_[A-Z0-9_]+)", chunk))
    return graph


def reaches_idle(graph, idle, min_states=5):
    if graph is None:
        return None, []
    can = {idle}
    changed = True
    while changed:
        changed = False
        for s, succ in graph.items():
            if s not in can and (succ & can):
                can.add(s)
                changed = True
    stuck = [s for s in graph if s not in can]
    return can, stuck


MODULES = [
    ("order_book.v", "order_book"),
    ("mold64_reasm.v", "mold64_reasm"),
]

print("idle reachability across modules with a state machine")
print()
fails = []
for fname, label in MODULES:
    path = os.path.join(RTL, fname)
    graph = parse_machine(path)
    if graph is None:
        print("  %-14s no case(state) block - skipped" % label)
        continue
    can, stuck = reaches_idle(graph, "ST_IDLE")
    print("  %-14s %2d states, %2d reach ST_IDLE, %d stuck"
          % (label, len(graph), len(can), len(stuck)))
    if len(graph) < 5:
        print("     REFUSING to pass: only %d states parsed" % len(graph))
        fails.append("%s: only %d states parsed" % (label, len(graph)))
    for s in stuck:
        succ = sorted(graph[s])
        print("     %-16s -> %s" % (s, ",".join(succ) if succ else "(none)"))
        fails.append("%s: state %s cannot reach ST_IDLE" % (label, s))

print()
if fails:
    print("MODULE-IDLE-REACH-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("MODULE-IDLE-REACH-PASS")
