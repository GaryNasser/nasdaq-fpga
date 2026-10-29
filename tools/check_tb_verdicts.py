"""Fail when the report claims a passing verdict for a superseded testbench.

Round 23 mishandled this badly: it saw that tb_mold64_reasm exists, that its first
line says "SUPERSEDED - THIS TESTBENCH HANGS", and concluded the FILE was deleted.
The file was always there. The real problem is the opposite one:

    section 3 lists  | `tb_mold64_reasm` | TB-ALL-PASS |

for a testbench whose own header says DO NOT USE IT AS A VERIFICATION GATE. A reader
sees a pass and assumes it runs. It hangs.

check_tb_refs only asks "does the file exist". This asks the stronger question: if a
testbench is marked SUPERSEDED / HANGS / DO NOT USE, the report must not present its
verdict as a current result without saying so.

A row that names the file is allowed to exist; it must carry the same warning, or the
sentence around it must.
"""
import io
import os
import re
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = r"D:\agent\nasdaq-fpga"
DOC = os.path.join(REPO, "docs", "final-report.md")
DIRS = [os.path.join(REPO, "tools"), os.path.join(REPO, "rtl", "itch")]

# Markers a testbench uses to disown itself.
SELF_WARN = re.compile(r"(SUPERSEDED|DO NOT USE|HANGS|OBSOLETE|DEPRECATED)", re.I)
# Language in the report that carries the same information.
DOC_WARN = re.compile(r"(已废弃|会挂起|挂起|不要使用|不可用|SUPERSEDED|HANGS)", re.I)


def find_tb(name):
    for d in DIRS:
        p = os.path.join(d, name + ".v")
        if os.path.exists(p):
            return p
    return None


def is_superseded(path):
    head = io.open(path, encoding="utf-8", errors="replace").read(1200)
    return bool(SELF_WARN.search(head))


text = io.open(DOC, encoding="utf-8", errors="replace").read()
lines = text.split("\n")

fails = []
checked = 0
print("testbenches disowned by their own header")

for i, line in enumerate(lines):
    for m in re.finditer(r"`(tb_[a-z0-9_]+)`", line):
        name = m.group(1)
        path = find_tb(name)
        if not path or not is_superseded(path):
            continue
        checked += 1
        # The report must warn in this line, the next two, or the previous two.
        window_lines = lines[max(0, i - 2):i + 3]
        window = "\n".join(window_lines)
        marker = SELF_WARN.search(io.open(path, encoding="utf-8",
                                          errors="replace").read(800))
        word = marker.group(0) if marker else "SUPERSEDED"
        warned = bool(DOC_WARN.search(window))
        status = "warned" if warned else "NO WARNING"
        print("  line %-4d %-22s %s" % (i + 1, name, status))
        if not warned:
            fails.append((i + 1, name, word))

print()
print("%d reference(s) to a self-disowned testbench" % checked)
if fails:
    print("TB-VERDICT-FAIL (%d)" % len(fails))
    for ln, name, word in fails:
        print("  line %d: %s is marked %s but the report gives it a verdict"
              % (ln, name, word))
    sys.exit(1)
print("TB-VERDICT-PASS")
