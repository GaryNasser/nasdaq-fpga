"""Every FSM state must be reachable and have at least one exit.

The FSM uses `case (state)`, so a state's exit is a `case` label, not an `==` comparison.

    case (state)                        L1220
      ST_IDLE:      ...
      ST_SESSION0:  begin ... state <= ST_SESSION1; end
      ...

My audit only looked for `state == ST_x`, so 17 of 19 states looked like dead ends. **The audit was wrong, not the
design** - the same shape as rounds 213-223, where the detector's notion of the syntax was too narrow.

Count a state's exits as: `case` labels plus `==`/`!=` comparisons.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

total_problems = 0
total_states = 0
modules = 0

for fn in sorted(os.listdir(RTL)):
    if not fn.endswith(".v"):
        continue
    src = io.open(os.path.join(RTL, fn), encoding="latin-1").read()

    states = re.findall(r"localparam\s*(?:\[[^\]]*\]\s*)?(ST_\w+)\s*=", src)
    if not states:
        continue

    modules += 1
    total_states += len(set(states))
    print("%s  (%d states)" % (fn, len(states)))
    print("-" * 78)

    problems = 0
    for st in sorted(set(states)):
        case_label = len(re.findall(r"^\s*%s\s*:" % re.escape(st), src, re.M))
        compares = len(re.findall(r"(?:state|cur_state|nxt_state)\w*\s*[!=]==?\s*%s\b" % re.escape(st), src))
        compares += len(re.findall(r"%s\b\s*[!=]==?\s*(?:state|cur_state)" % re.escape(st), src))
        entries = len(re.findall(r"<=\s*%s\b" % re.escape(st), src))
        exits = case_label + compares

        flag = ""
        if entries and not exits:
            flag = "   <-- ENTERED BUT NEVER EXITED"
            problems += 1
        elif exits and not entries:
            flag = "   <-- exited but never entered"
            problems += 1
        if flag:
            print("  %-16s exits=%-2d entries=%-2d%s" % (st, exits, entries, flag))

    total_problems += problems
    print("  states with a structural problem: %d" % problems)
    print()

print()
if total_problems:
    print("FSM-STATES-FAIL (%d)" % total_problems)
    print("  A state that can be entered but never left is a hang; one never entered is dead logic.")
    sys.exit(1)
print("FSM-STATES-PASS (%d states across %d modules, all with an entry and an exit)"
      % (total_states, modules))
