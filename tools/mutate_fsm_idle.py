"""Mutate the FSM using the exact lines the file contains.

The first attempt found `ST_LEV_CHK:` inside a comment header, and `re.search` with a
non-greedy quantifier then captured a span that did not include the transition line - so
the replacement silently did nothing and `landed` was False for both mutations.

The arms in the file are short and uniform:

    ST_LEV_CHK: begin
      lev_depleted_r <= (lev_rshares <= ev_shares);
      state <= ST_LEV_UPDATE;
    end

so a literal replacement of the transition line is both simpler and exact. To keep the
mutation unambiguous, the replacement includes the surrounding two lines.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

OB = r"D:\agent\nasdaq-fpga\rtl\itch\order_book.v"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_fsm_idle_reach.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".v")
shutil.copyfile(OB, backup)
original = io.open(OB, encoding="latin-1").read()

PAIRS = [
    ("ST_LEV_CHK self-loop",
     "          lev_depleted_r <= (lev_rshares <= ev_shares);\n"
     "          state <= ST_LEV_UPDATE;",
     "          lev_depleted_r <= (lev_rshares <= ev_shares);\n"
     "          state <= ST_LEV_CHK;"),
]

# ST_BBO's return: find its arm text.
import re
m = re.search(r"ST_BBO: begin(.*?)\n        end", original, re.S)
if m:
    arm = m.group(1)
    new_arm = re.sub(r"state\s*<=\s*ST_IDLE", "state <= ST_MAP_WRITE", arm)
    if new_arm != arm:
        PAIRS.append(("ST_BBO diverted (transitive)",
                      "ST_BBO: begin" + arm,
                      "ST_BBO: begin" + new_arm))

results = []
for name, old, new in PAIRS:
    mutated = original.replace(old, new, 1)
    landed = mutated != original
    io.open(OB, "w", encoding="latin-1", newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-32s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(OB, "w", encoding="latin-1", newline="\n").write(original)

restored = io.open(OB, encoding="latin-1").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, OB)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("FSM-IDLE-REACH-MUTATION-PASS")
else:
    print("FSM-IDLE-REACH-MUTATION-FAIL")
