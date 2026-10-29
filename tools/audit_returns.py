"""Fourth version: recognise the reference-capture guard as a legitimate skip.

History of this audit, each version killed by testing it:

  1. text-based      - mutation `if nmsg != 43428: print("count wrong"); return 0`
                       passed, because the message had no alarming word.
  2. require args.   - too strict: flagged the ordinary success returns.
  3. data conditions - correct in principle, but flagged line 560, which is the
                       ALREADY-FIXED branch:

                           if ref:
                               print(...); return 6     <- reference input fails
                           print(...); return 0          <- other input: skip

                       The `return 0` is correct there; what makes it correct is
                       that a `return 6` for the reference case precedes it in the
                       same block.

So the rule needs one more clause: a `return 0` under a data condition is acceptable
when the same block contains a non-zero return guarded by the reference test. That is
exactly the shape round 19 introduced, and its absence is the defect.

This is what a check looks like when it is developed by attacking it rather than by
writing it and hoping.
"""
import io
import re
import sys

PATH = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
lines = io.open(PATH, encoding="utf-8").read().split("\n")


def indent_of(s):
    return len(s) - len(s.lstrip())


def enclosing_condition(idx):
    depth = indent_of(lines[idx])
    for j in range(idx - 1, -1, -1):
        l = lines[j]
        if not l.strip():
            continue
        if indent_of(l) < depth:
            s = l.strip()
            if s.startswith("if ") or s.startswith("elif "):
                cond = s
                k = j + 1
                while not cond.rstrip().endswith(":") and k < len(lines):
                    cond += " " + lines[k].strip()
                    k += 1
                return cond, j + 1
            return None, None
    return None, None


CALLER = re.compile(r"\bargs\.\w+|\bgetattr\(\s*args\b")
DATA = re.compile(r"\b(nmsg|rx_packets|bytes_in|bytes_out|gap_count|m64_errors|"
                  r"counters|mismatches|drop_count|error_count)\b")
REF_GUARD = re.compile(r"_is_reference_capture|REFERENCE_CAPTURE|ref\b")


def block_has_reference_failure(idx, cond_line):
    """Does the block containing a return at idx also fail on the reference input?"""
    # Look from the enclosing if to the end of its block for a non-zero return
    # guarded by the reference test.
    depth = indent_of(lines[cond_line - 1])
    for j in range(cond_line - 1, len(lines)):
        l = lines[j]
        if l.strip() and indent_of(l) < depth and j > cond_line - 1:
            break
        if REF_GUARD.search(l) and "if " in l:
            # Does a non-zero return follow within a few lines?
            for k in range(j + 1, min(len(lines), j + 8)):
                m = re.match(r"^\s*return (\d+)\s*$", lines[k])
                if m:
                    if int(m.group(1)) != 0:
                        return True
                    break
    return False


fails = []
rows = 0
print("return 0 statements, judged by guard nature")
print()

for i, line in enumerate(lines):
    if not re.match(r"^\s*return 0\s*$", line):
        continue
    rows += 1
    cond, cline = enclosing_condition(i)
    if cond is None:
        print("  line %-4d unconditional success                OK" % (i + 1))
        continue
    if CALLER.search(cond):
        print("  line %-4d caller-chosen flag                   OK" % (i + 1))
        continue
    if DATA.search(cond):
        if block_has_reference_failure(i, cline):
            print("  line %-4d data guard, but the reference case "
                  "fails first  OK" % (i + 1))
            continue
        print("  line %-4d DATA GUARD with no reference failure : %s"
              % (i + 1, cond.strip()[:52]))
        fails.append((i + 1, cond))
        continue
    print("  line %-4d guard: %-34s (not a data test)"
          % (i + 1, cond.strip()[:34]))

print()
print("%d return 0 statements examined" % rows)
if fails:
    print("RETURN-AUDIT-FAIL (%d)" % len(fails))
    for ln, c in fails:
        print("  line %d: %s" % (ln, (c or "").strip()[:80]))
    sys.exit(1)
print("RETURN-AUDIT-PASS")
