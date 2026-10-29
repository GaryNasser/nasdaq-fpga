"""Mutate by POSITION, not by text.

`state <= ST_SESSION0` appears in more than one arm, so a literal replacement hits the
wrong one and the mutation either does nothing or corrupts a different state.

The reliable approach: locate the ST_SESSION_CHK arm with a begin/end depth scan (exactly
as the check does), then rewrite every `state <=` inside that span in place, using the
offsets of the original file.

This is the same principle as the scope rule that has recurred throughout: work on the
span that must contain the fact, not on a string that might.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

RTL = r"D:\agent\nasdaq-fpga\rtl\itch\mold64_reasm.v"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_module_idle_reach.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".v")
shutil.copyfile(RTL, backup)
# Round 253: interruption-safe restore. A killed run must not leave a source file modified.
import atexit as _atexit
_atexit.register(lambda _d=RTL, _b=backup: os.path.exists(_b) and shutil.copyfile(_b, _d))

original = io.open(RTL, encoding="latin-1").read()


def mask_comments(text):
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


masked = mask_comments(original)


def arm_span(label):
    m = re.search(r"\b%s\s*:\s*begin\b" % label, masked)
    if not m:
        return None
    d = 1
    for tm in re.finditer(r"\b(begin|end)\b", masked[m.end():]):
        d += 1 if tm.group(1) == "begin" else -1
        if d == 0:
            return (m.end(), m.end() + tm.start())
    return None


def self_loop_mutation(label):
    span = arm_span(label)
    if span is None:
        return None
    s, e = span
    body = original[s:e]
    # Replace every state assignment in the span with a loop to `label`.
    new_body, n = re.subn(r"state\s*<=\s*(ST_\w+)", "state <= %s" % label, body)
    if not n:
        return None
    return original[:s] + new_body + original[e:], n


TARGETS = ["ST_SESSION_CHK", "ST_SEQ_LO", "ST_SESSION3"]
results = []
for label in TARGETS:
    made = self_loop_mutation(label)
    if not made:
        print("%-18s could not build a mutation" % label)
        results.append((label, False, False))
        continue
    mutated, n = made
    io.open(RTL, "w", encoding="latin-1", newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((label, True, caught))
    print("%-18s %d assignment(s) looped  exit=%d %s"
          % (label, n, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(RTL, "w", encoding="latin-1", newline="\n").write(original)

restored = io.open(RTL, encoding="latin-1").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, RTL)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("MODULE-IDLE-REACH-MUTATION-PASS")
else:
    print("MODULE-IDLE-REACH-MUTATION-FAIL")
    sys.exit(1)
