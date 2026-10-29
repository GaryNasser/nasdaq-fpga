"""Check that every claim about the driver's flags is backed by the driver's code.

`--legacy-reset` is documented as "use the old single-write CTRL=0x3 reset+enable;
this loses one 8-byte word from the first packet (kept to demonstrate the defect)".

That is a strong claim: it says the flag reproduces a specific hardware failure. If
the flag ever stops doing that - because the code was refactored, or because it only
applies to one of the two code paths - the help text becomes a lie that a reader
would believe.

This verifies, structurally:

  * --legacy-reset exists and its help mentions the defect;
  * it gates EVERY CTRL write that precedes a transfer, not just one;
  * the default path uses 0x2 -> 0x1;
  * the flag is actually read somewhere (a declared but unused flag is dead code).
"""
import io
import re
import sys

PATH = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
lines = io.open(PATH, encoding="utf-8").read().split("\n")

fails = []
print("driver flag audit")
print()

# 1. declared, with a help text naming the defect
# A DECLARATION is an add_argument call, not any mention of the string. The driver also
# names the flag in a comment (L435) and reads it as args.legacy_reset; counting either as a
# declaration let the check pass with the flag undeclared.
decl = [i for i, l in enumerate(lines)
        if re.search(r"add_argument\(\s*['\"]--legacy-reset['\"]", l)]
if not decl:
    fails.append("--legacy-reset is not declared")
    print("  declared         : NO")
else:
    print("  declared         : line %d" % (decl[0] + 1))
    window = "\n".join(lines[decl[0]:decl[0] + 5])
    if "defect" in window.lower() or "loses" in window.lower():
        print("  help names the defect: yes")
    else:
        fails.append("--legacy-reset help does not explain what it demonstrates")
        print("  help names the defect: NO")

# 2. read somewhere
uses = [i for i, l in enumerate(lines)
        if re.search(r"args\.legacy_reset", l)]
print("  read in code     : %d place(s)" % len(uses))
if not uses:
    fails.append("--legacy-reset is never read (dead flag)")

# 3. find every 0x3 write and confirm each sits inside a legacy_reset branch
three = [i for i, l in enumerate(lines)
         if re.search(r"REG_M64_CTRL\s*,\s*0x3\b", l)]
print("  CTRL=0x3 writes  : %d" % len(three))
for i in three:
    # Walk upward to the nearest "if args.legacy_reset" or a non-indented line.
    guarded = False
    depth = len(lines[i]) - len(lines[i].lstrip())
    for j in range(i - 1, max(-1, i - 40), -1):
        lj = lines[j]
        if not lj.strip():
            continue
        ind = len(lj) - len(lj.lstrip())
        if ind < depth:
            if "legacy_reset" in lj:
                guarded = True
            break
    if not guarded:
        fails.append("CTRL=0x3 at line %d is not inside a legacy_reset branch"
                     % (i + 1))
        print("    line %-5d UNGUARDED" % (i + 1))
    else:
        print("    line %-5d guarded by --legacy-reset" % (i + 1))

# 4. the default path resets then enables
pairs = 0
for i, l in enumerate(lines):
    if re.search(r"REG_M64_CTRL\s*,\s*0x2\b", l):
        for j in range(i + 1, min(len(lines), i + 12)):
            if re.search(r"REG_M64_CTRL\s*,\s*0x1\b", lines[j]):
                pairs += 1
                break
print("  0x2->0x1 pairs   : %d" % pairs)
if pairs == 0:
    fails.append("no reset-then-enable pair found in the default path")

print()
if fails:
    print("FLAG-AUDIT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("FLAG-AUDIT-PASS")
