"""The comparison is meaningless: it applies both patterns to both checks.

    check_fsm_idle_reach uses STRICT over order_book.v      - correct, no digits there
    check_module_idle_reach uses LOOSE over both modules     - correct, digits handled

Applying STRICT to mold64_reasm "finds" a truncation that check never performs. That is not
drift; it is the check reporting a hypothetical.

The property actually worth checking is: **does each check's pattern handle the names in the
files it scans?** So for each check, use ITS OWN pattern - read from its source - over its own
files. If its pattern truncates a name it must read, that is a live bug.

Reading each check's real pattern from its source, rather than assuming which is which.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch")
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHECKS = {
    "check_fsm_idle_reach.py": ["order_book.v"],
    "check_module_idle_reach.py": ["order_book.v", "mold64_reasm.v"],
}


def strip(code):
    code = re.sub(r"//[^\n]*", "", code)
    return re.sub(r"/\*.*?\*/", "", code, flags=re.S)


print("does each check's own token pattern handle the names in the files it scans?")
print()

fails = []
for check, files in CHECKS.items():
    src = io.open(os.path.join(TOOLS, check), encoding="utf-8").read()
    # The tokeniser it actually compiles.
    m = re.search(r'TOKEN\s*=\s*re\.compile\(\s*r?"(.*?)"\s*\)', src, re.S)
    if not m:
        m = re.search(r're\.compile\(\s*r"(\\b\(begin\|end[^"]*)"', src)
    pat_src = m.group(1) if m else None
    if not pat_src:
        print("  %-28s could not read its token pattern" % check)
        continue
    pat_src = pat_src.replace("\\\\", "\\")
    token = re.compile(pat_src)

    truncations = []
    for f in files:
        p = os.path.join(RTL, f)
        if not os.path.exists(p):
            continue
        code = strip(io.open(p, encoding="latin-1").read())
        declared = set(re.findall(r"\b(ST_[A-Za-z0-9_]+)\b", code))
        seen = set(x.group(1) for x in token.finditer(code)
                   if x.group(1).startswith("ST_"))
        lost = sorted(n for n in declared if n not in seen
                      and any(n.startswith(s) for s in seen))
        if lost:
            truncations.append((f, lost))

    if truncations:
        for f, lost in truncations:
            print("  %-28s TRUNCATES %d name(s) in %s: %s"
                  % (check, len(lost), f, ",".join(lost[:3])))
            fails.append(check)
    else:
        print("  %-28s handles every name in %s"
              % (check, ", ".join(files)))

print()
if fails:
    print("PATTERN-SCOPE-FAIL (%d): a check truncates a state name it must read"
          % len(fails))
    for c in fails:
        print("  %s" % c)
    sys.exit(1)
print("PATTERN-SCOPE-PASS (each check's pattern covers the names in its own files)")
