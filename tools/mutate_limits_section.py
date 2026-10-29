"""Effective mutations for the item-scoped limits check.

The previous pair was invalid:

  * removing 3 of 14 items left 11, far above the threshold - the check never entered a
    failing state;
  * the DMA greeting string existed but the cause also appeared in the correction
    blockquote, which the check counted as part of an item.

The check now excludes blockquotes and requires four items. New mutations:

  1. strip the cause words from the DMA item, leaving the gap named
  2. strip the pin/MIO words from the K1 item
  3. cut the section down to two items
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_limits_section.py"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=REPORT, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()


def strip_section(text, new_body_fn):
    lines = text.split("\n")
    FENCE = "`" * 3
    inblock = False
    start = None
    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith(FENCE):
            inblock = not inblock
            continue
        if not inblock and re.match(r"^#{1,2} .*已知限制", l):
            start = i
            break
    if start is None:
        return None
    inblock = False
    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith(FENCE):
            inblock = not inblock
            continue
        if not inblock and re.match(r"^#{1,2} ", lines[j]):
            end = j
            break
    body = lines[start + 1:end]
    return "\n".join(lines[:start + 1] + new_body_fn(body) + lines[end:])


def drop_dma_cause(body):
    out = []
    for l in body:
        if "S2MM" in l or "旁路" in l:
            l = l.replace("S2MM", "某组件").replace("旁路", "某路径")
        out.append(l)
    return out


def drop_k1_cause(body):
    out = []
    for l in body:
        if "引脚" in l or "MIO" in l:
            l = l.replace("引脚", "条件").replace("MIO", "接口")
        out.append(l)
    return out


def cut_to_two(body):
    kept, seen = [], 0
    for l in body:
        if re.match(r"^\d+\.\s", l) or re.match(r"^[*+-]\s", l):
            seen += 1
            if seen > 2:
                continue
        kept.append(l)
    return kept


MUTATIONS = [
    ("strip the DMA cause", lambda t: strip_section(t, drop_dma_cause)),
    ("strip K1's pin cause", lambda t: strip_section(t, drop_k1_cause)),
    ("cut to two items", lambda t: strip_section(t, cut_to_two)),
]

results = []
for name, fn in MUTATIONS:
    mutated = fn(original)
    landed = mutated is not None and mutated != original
    if not landed:
        results.append((name, False, False))
        print("%-24s landed=False (no change)" % name)
        continue
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-24s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(original)

restored = io.open(REPORT, encoding="utf-8",
                   errors="surrogateescape").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, REPORT)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("LIMITS-SECTION-MUTATION-PASS")
else:
    print("LIMITS-SECTION-MUTATION-FAIL")
    sys.exit(1)
