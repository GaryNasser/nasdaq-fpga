"""Confirm check_section_content catches a section losing its promised content.

Mutations:
  1. delete the throughput table          -> 吞吐 must FAIL
  2. delete the reproduction code block   -> 复现 must FAIL
  3. delete the limitations list          -> 已知限制 must FAIL
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_section_content.py"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()


def rewrite_section(text, title_sub, transform):
    """Apply transform to the body of the top-level section whose title contains title_sub."""
    lines = text.split("\n")
    FENCE = "`" * 3
    inblock = False
    start = None
    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith(FENCE):
            inblock = not inblock
            continue
        if not inblock and re.match(r"^#{1,2} ", l) and title_sub in l:
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
    body = "\n".join(lines[start + 1:end])
    new_body = transform(body)
    return "\n".join(lines[:start + 1] + [new_body] + lines[end:])


def drop_table(b):
    return "\n".join(l for l in b.split("\n") if not l.strip().startswith("|"))


def drop_fences(b):
    out, inb = [], False
    for l in b.split("\n"):
        if l.strip().startswith("`" * 3):
            inb = not inb
            continue
        if not inb:
            out.append(l)
    return "\n".join(out)


def drop_list(b):
    return "\n".join(l for l in b.split("\n")
                     if not re.match(r"^\s*[*-] ", l))


MUTATIONS = [
    ("drop the throughput table", lambda t: rewrite_section(t, "吞吐", drop_table)),
    ("drop the reproduction code", lambda t: rewrite_section(t, "复现", drop_fences)),
    ("drop the limitations list", lambda t: rewrite_section(t, "已知限制", drop_list)),
]

results = []
for name, fn in MUTATIONS:
    mutated = fn(original)
    landed = mutated is not None and mutated != original
    if not landed:
        results.append((name, False, False))
        print("%-30s landed=%-5s (section not found)" % (name, landed))
        continue
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-30s landed=%-5s exit=%d %s"
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
    print("SECTION-CONTENT-MUTATION-PASS")
else:
    print("SECTION-CONTENT-MUTATION-FAIL")
    sys.exit(1)
