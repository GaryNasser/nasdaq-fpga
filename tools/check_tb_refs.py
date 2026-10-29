"""Fail if the report names a testbench file that does not exist.

Section 3 of the report claimed four testbenches produced TB-ALL-PASS:

    tb_mold64_reasm, tb_itch_parse, tb_order_book, tb_ts_hist

Only the last exists. Section 9.1 compounded it by saying three of them "仍然有效" -
two of those were not on disk either. A reader following the reproduction
instructions would search for files deleted in the byte-FIFO rewrite.

DISCRIMINATING CHECKERS FROM TESTBENCHES

Two earlier attempts got this wrong in opposite directions:

  1. matching any `tb_*` token flagged the checker named `tb_refs` in the check
     table;
  2. skipping any table row whose first cell is backticked then let a planted
     `| \`tb_ghost_test\` | TB-ALL-PASS |` through.

The right discriminator is the NAME, not the row shape: if it appears in
run_checks.py's CHECKS table it is a checker; otherwise it is a claim about a file
and the file must exist.

Historical notes ("已不在仓库中", "已删除", "被取代") are allowed to name missing files,
because the document is correctly recording that they are gone.
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
DOCS = ["docs/final-report.md", "docs/status.md"]
SEARCH_DIRS = [os.path.join(REPO, "tools"), os.path.join(REPO, "rtl", "itch")]

TB = re.compile(r"\b(tb_[a-z0-9_]+)\b")
GONE = re.compile(r"(不在仓库|已删除|已被删除|不再存在|被取代|MISSING|removed|deleted|"
                  r"superseded|不存在)", re.I)

# Names of the CHECKS in run_checks.py - checkers, not testbenches.
rc = io.open(os.path.join(REPO, "tools", "run_checks.py"), encoding="utf-8").read()
CHECK_NAMES = set(re.findall(r'\(\s*"(\w+)",\s*"[^"]*"', rc))
# Belt and braces: names that are checkers regardless of how the table is parsed.
CHECK_NAMES |= {
    "reference_id", "golden_paths", "return_paths", "suite_asserts", "tb_refs",
    "warmup_advice", "t1_claims", "deliverables", "ctrl_sequence", "repro_doc",
    "tool_claims", "flag_audit", "transfer_reset", "board_claims",
}


def exists(name):
    return any(os.path.exists(os.path.join(d, name + ".v")) for d in SEARCH_DIRS)


fails = []
checked = 0
skipped = set()
print("testbench names in the documents")

for rel in DOCS:
    path = os.path.join(REPO, rel)
    if not os.path.exists(path):
        continue
    text = io.open(path, encoding="utf-8", errors="replace").read()
    lines = text.split("\n")
    for i, line in enumerate(lines):
        for m in TB.finditer(line):
            name = m.group(1)
            if name in CHECK_NAMES:
                skipped.add(name)
                continue
            checked += 1
            if exists(name):
                continue
            window = "\n".join(lines[max(0, i - 2):i + 3])
            if GONE.search(window):
                continue
            fails.append((rel, i + 1, name))
            print("  %s:%d names %s, which is not on disk" % (rel, i + 1, name))

print()
print("checked %d name(s); skipped %d checker name(s)" % (checked, len(skipped)))
if fails:
    print("TB-REF-FAIL (%d)" % len(fails))
    for rel, ln, name in fails:
        print("  %s:%d %s" % (rel, ln, name))
    sys.exit(1)
print("TB-REF-PASS")
