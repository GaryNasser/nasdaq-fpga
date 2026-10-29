"""Does each top-level section carry the content its title promises?

The reader-view audit counted characters, which treats a section that is all subsections
as empty and one that is all prose as full. Neither is what matters.

What matters: does section N answer the question its title asks?

    5.  吞吐（M7 / K2）      -> numbers for throughput, and K2's status
    9.  复现                  -> commands that reproduce the results
    8.  已知限制              -> limits, each with a reason
    4.1b 时序余量             -> margins with context

This extracts the top-level sections and reports, for each, whether it contains the
kinds of element its title implies - a table or figure for a results section, a code
block for a reproduction section, and so on.
"""
import io
import re
import sys

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

lines = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read().split("\n")

# Fence-aware heading scan.
FENCE = "`" * 3
inblock = False
heads = []
for i, l in enumerate(lines):
    s = l.strip()
    if s.startswith(FENCE):
        inblock = not inblock
        continue
    m = re.match(r"^(#{1,3}) (.+)$", l)
    if m and not inblock:
        heads.append((i, len(m.group(1)), m.group(2).strip()))

# Top-level: '#' and '##'.
tops = [(i, h) for i, lvl, h in heads if lvl <= 2]

REQUIREMENTS = {
    "吞吐": ("table", "MB/s"),
    "复现": ("code", "python"),
    "已知限制": ("list", None),
    "时序": ("number", "ns"),
    "平台": ("table", None),
    "资源": ("table", None),
}

print("do top-level sections carry what their titles promise?")
print()
fails = []

for k, (i, title) in enumerate(tops):
    end = tops[k + 1][0] if k + 1 < len(tops) else len(lines)
    body = "\n".join(lines[i + 1:end])
    has_table = "| ---" in body
    has_code = body.count(FENCE) >= 2
    has_list = bool(re.search(r"^\s*[*-] ", body, re.M))
    n_chars = len(body.strip())

    kind = None
    for key in REQUIREMENTS:
        if key in title:
            kind = key
            break

    status = ""
    if kind == "吞吐":
        ok = has_table and "MB/s" in body
        status = "table+rate" if ok else "MISSING table or rate"
    elif kind == "复现":
        ok = has_code
        status = "commands" if ok else "MISSING code block"
    elif kind == "已知限制":
        ok = has_list or "| ---" in body
        status = "enumerated" if ok else "MISSING enumeration"
    elif kind == "时序":
        ok = bool(re.search(r"-?\d+\.\d+\s*ns", body))
        status = "numbers" if ok else "MISSING numeric margins"
    elif kind == "资源":
        ok = has_table
        status = "table" if ok else "MISSING table"
    else:
        ok = n_chars > 0
        status = "%d chars" % n_chars

    print("  %-34s %-24s %s" % (title[:34], status, "" if ok else "<--"))
    if not ok:
        fails.append((title, status))

print()
if fails:
    print("SECTION-CONTENT-FAIL (%d)" % len(fails))
    for t, s in fails:
        print("  %s: %s" % (t, s))
    sys.exit(1)
print("SECTION-CONTENT-PASS (each titled section carries its promised content)")
