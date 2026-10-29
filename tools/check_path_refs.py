"""Don't let a FILENAME containing "deleted" excuse a missing file.

The mutation planted

    复现需要运行 `scripts/deleted_helper.py`。

and the check passed. The path was found, did not exist, and yet GONE matched -
because the filename contains the word "deleted". A file called
`deleted_helper.py` is not a historical note.

Two fixes:

  * apply GONE to the SURROUNDING prose only, with the path text removed, so words
    inside the reference cannot excuse it;
  * drop the bare English words (deleted/removed/MISSING) from the prose pattern
    too, since prose in this document is Chinese and an English word in a Chinese
    sentence is far more likely to be part of an identifier than a statement about
    history. Keep the Chinese phrases, which are unambiguous.

Also repair the earlier finding that a leading "/" was stripped by .lstrip("./"),
which turned an absolute on-board path into a relative one. lstrip takes a CHARACTER
SET, not a prefix - a classic bug that silently mangled "/home/xilinx/...".
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
DOC = os.path.join(REPO, "docs", "final-report.md")

PATHISH = re.compile(
    r"((?:~|\.{0,2}/)?(?:[\w.\-]+/)+[\w.\-]+\.(?:py|v|tcl|md|hwh|bit|json|hex|txt|csv|raw|mold64))")

# Chinese phrases about removal. English words are excluded: they collide with
# identifiers ("deleted_helper.py") far more often than they express history.
GONE = re.compile(r"(已删除|已被删除|不再存在|被取代|已移除|不存在)", re.I)

# Absolute on-board paths. A leading "/" alone is NOT remote: the report writes
# "<repo>/rtl/itch/foo.v" and the regex sees only "/rtl/itch/foo.v". Those are
# repository-relative once the <repo> placeholder is accounted for.
REMOTE = ("/home/", "~/", "/usr/", "/tmp/", "home/")

# Directory names that follow a "<repo>/" placeholder in the report.
REPO_DIRS = ("/rtl/", "/tools/", "/board/", "/vivado/", "/docs/",
             "/scripts/", "/data/", "/host/")
RUNTIME_DIRS = ("nasdaq_realfile/", "workspace/out/", "xsim.dir/", "work/")
ALLOW_MISSING = {
    "vivado/out/nasdaq.bit",
    "vivado/out/nasdaq.hwh",
}


def strip_prefix(ref):
    """Remove a leading ./ or ../ without lstrip's character-set surprise."""
    if ref.startswith("./"):
        return ref[2:]
    if ref.startswith("../"):
        return ref[3:]
    return ref


text = io.open(DOC, encoding="utf-8", errors="replace").read()
lines = text.split("\n")

fails = []
seen = set()
checked = 0
skipped = 0
print("repository path references in the report")

for i, line in enumerate(lines):
    for m in PATHISH.finditer(line):
        raw = m.group(1)
        if raw.startswith(REMOTE):
            skipped += 1
            continue
        if any(d in raw for d in RUNTIME_DIRS):
            skipped += 1
            continue

        # "<repo>/rtl/x.v" arrives as "/rtl/x.v": a leading slash followed by a
        # known repo directory is a placeholder, not an absolute path.
        if raw.startswith(REPO_DIRS):
            raw = raw[1:]

        ref = strip_prefix(raw).rstrip(".,);:")
        if ref in seen:
            continue
        seen.add(ref)
        checked += 1

        if ref in ALLOW_MISSING:
            continue
        if os.path.exists(os.path.join(REPO, ref.replace("/", os.sep))):
            continue

        # Judge the surrounding prose with the reference itself removed, so words
        # inside a filename cannot excuse a missing file.
        window_lines = lines[max(0, i - 2):i + 3]
        window = "\n".join(window_lines)
        prose = window.replace(raw, " ")
        if GONE.search(prose):
            continue

        fails.append((i + 1, ref))
        print("  line %-4d %s  (not on disk)" % (i + 1, ref))

print()
print("checked %d repository path(s); skipped %d remote/runtime path(s)"
      % (checked, skipped))
if fails:
    print("PATH-REF-FAIL (%d)" % len(fails))
    for ln, ref in fails:
        print("  line %d: %s" % (ln, ref))
    sys.exit(1)
print("PATH-REF-PASS")
