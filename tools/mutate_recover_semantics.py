"""Confirm check_recover_semantics catches each qualification being removed.

Mutations scoped to section 1.z specifically, since round 37 showed that a document-wide
search can be satisfied by an unrelated mention.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_recover_semantics.py"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=REPORT, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()


def bounds(text):
    m = re.search(r"###\s*1\.z[^\n]*", text)
    if not m:
        return None
    nxt = re.search(r"\n###\s", text[m.end():])
    end = m.end() + nxt.start() if nxt else len(text)
    return m.start(), end


def edit(fn):
    b = bounds(original)
    if b is None:
        return original
    s, e = b
    return original[:s] + fn(original[s:e]) + original[e:]


MUTATIONS = [
    ("drop the RTL-identity reason",
     edit(lambda t: t.replace("代码逐字节一致", "代码没有变化", 1))),
    ("drop the 'not the same' clause",
     edit(lambda t: t.replace("不是同一句话", "两者相关", 1))),
    ("drop the supported claim",
     edit(lambda t: t.replace("通过了 golden 比对", "运行成功", 1))),
]
# Round 13: bounds() returns None when the section is absent, and indexing it crashed the whole proof.
# A proof run against a document without that section should report that fact, not die.
_b = bounds(original)
if _b is None:
    print("MUTATE-RECOVER-SEMANTICS-INCONCLUSIVE: the target section is absent")
    MUTATIONS = []
else:
    MUTATIONS.append(("remove the whole section", original[:_b[0]] + original[_b[1]:]))

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-32s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(original)

restored = io.open(REPORT, encoding="utf-8",
                   errors="surrogateescape").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, REPORT)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("RECOVER-SEM-MUTATION-PASS")
else:
    print("RECOVER-SEM-MUTATION-FAIL")
    sys.exit(1)
