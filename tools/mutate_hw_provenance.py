"""Fix the mutation script: it edited the WRONG occurrence of the MD5.

`str.replace(old, new, 1)` replaces the FIRST occurrence. The MD5 appears twice in the
report:

    pos 8591   in section 1.x  (describes the shipped bitstream)
    pos ~10376 in section 1.y  (the provenance statement)

So "drop the MD5" removed the one in 1.x and left the one in 1.y - the check correctly
found it in the section and passed. The checker was right; the test was wrong.

Same for the heading mutation: replacing "板上数字对应哪一份构建" hit the heading text,
but the check locates the section by the literal "1.y", which the mutation left intact.
That one needs a mutation that actually attacks what the check asserts.

Rewritten mutations:

  1. delete the MD5 from section 1.y specifically
  2. delete the whole section 1.y heading (so the section cannot be found)
  3. drop 仅推断 from 1.y
  4. drop board_recover.py from 1.y
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_hw_provenance.py"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=REPORT, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()


def section_bounds(text):
    m = re.search(r"###\s*1\.y[^\n]*", text)
    if not m:
        return None
    nxt = re.search(r"\n###\s", text[m.end():])
    end = m.end() + nxt.start() if nxt else len(text)
    return m.start(), end


def edit_section(fn):
    b = section_bounds(original)
    if b is None:
        return original
    s, e = b
    return original[:s] + fn(original[s:e]) + original[e:]


MUTATIONS = [
    ("delete MD5 in 1.y",
     edit_section(lambda t: re.sub(r"\b4BB3D7D1[0-9A-F]{24}\b", "the shipped build", t))),
    ("delete 1.y heading",
     edit_section(lambda t: t.replace("### 1.y", "### appendix", 1))),
    # Replace EVERY occurrence: the section states the distinction twice (once in the
    # "已测量 与 仅推断" heading of the paragraph, once in the sentence itself), and a
    # count=1 replacement left the second one in place, so removing "the distinction"
    # removed nothing the check looks for and the mutation was reported as MISSED.
    ("drop measured/inferred in 1.y",
     edit_section(lambda t: t.replace("仅推断", "推断"))),
    ("drop action in 1.y",
     edit_section(lambda t: t.replace("board_recover.py", "the tool", 1))),
]

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-30s landed=%-5s exit=%d %s"
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
    print("HW-PROV-MUTATION-PASS")
else:
    print("HW-PROV-MUTATION-FAIL")
    sys.exit(1)
