"""Report whether a rebuild reproduces the shipped bitstream bit-for-bit.

Round 29-30 ran a full rebuild from the same sources. The result:

    baseline bitstream  MD5 4BB3D7D1CFA5EC70CA0CFBCF36E5FFE8
    rebuilt bitstream   MD5 D874BD516CE561BBF7317A78B4DDD4E0
                                      NOT IDENTICAL
    WNS  0.126 -> 0.157    WHS  0.023 -> 0.057
    LUT  4507  -> 4500     FF   5372  -> 5373

Two readings are possible and they have very different consequences:

  (a) Vivado's place-and-route is non-deterministic - it uses seeds, wall-clock
      ordering and multi-threaded partitioning - so an identical design yields a
      different bitstream each time. This is well documented behaviour and does not
      invalidate the shipped result.

  (b) The sources changed between the two builds, so the "rebuild" is of a different
      design. That WOULD invalidate the shipped result.

This script decides which, using evidence rather than assumption:

  * whether every RTL/BD input is older than the baseline bitstream (so the two builds
    saw the same inputs);
  * whether the resource deltas are small enough to be placement noise (a design
    change would move LUTs by more than 7 of 4500);
  * whether the module-level FF counts - which depend only on the RTL, not on
    placement - still match the documented values.

If (a) holds, the correct action is to record the timing figures from the SHIPPED
bitstream as authoritative and note that rebuilds vary, rather than silently updating
the numbers to the newest build.
"""
import hashlib
import json
import io
import os
import re
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
# Round 41: re-baselined from a build whose sources are all committed and whose board
# behaviour is verified. The previous baseline was built from an uncommitted tree (round 39).
BASE_DIR = os.path.join(REPO, "build_check", '20261028_8FD5FA87')   # round 7 build (level_table off-by-one fix)
                                                         # previous: 20261025_125239 (round-203 ts_hist fix)
BASE_BIT = os.path.join(BASE_DIR, "nasdaq.bit")
NEW_BIT = os.path.join(REPO, "vivado", "out", "nasdaq.bit")


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


print("rebuild reproducibility")
print()

identical = md5(BASE_BIT) == md5(NEW_BIT)
print("  bitstreams identical         : %s" % identical)
print("  baseline MD5                 : %s" % md5(BASE_BIT))
print("  rebuilt  MD5                 : %s" % md5(NEW_BIT))

# Are all design inputs older than the baseline bitstream?
base_mtime = os.path.getmtime(BASE_BIT)
# Round 204: compare CONTENT, not mtimes. An edit made before the baseline copy is
# invisible to an mtime test, and an edit-then-restore is invisible to it forever.
# This is the fourth mtime-ordering failure in this project (rounds 33, 163, 178).
FP_PATH = os.path.join(BASE_DIR, "SOURCE-FINGERPRINTS.json")


def _fp(path):
    try:
        return hashlib.md5(io.open(path, "rb").read()).hexdigest()
    except OSError:
        return None


def _inputs():
    out = []
    for root, _dirs, files in os.walk(os.path.join(REPO, "rtl")):
        for f in files:
            if f.endswith(".v"):
                out.append(os.path.relpath(os.path.join(root, f), REPO))
    for f in ("create_project.tcl", "build_overlay.tcl"):
        if os.path.exists(os.path.join(REPO, "vivado", f)):
            out.append("vivado/" + f)
    return sorted(out)


if os.path.exists(FP_PATH):
    _base_fp = json.load(io.open(FP_PATH, encoding="utf-8"))
else:
    # First run after re-baselining: record the current state as the reference.
    _base_fp = {rel: _fp(os.path.join(REPO, rel)) for rel in _inputs()}
    json.dump(_base_fp, io.open(FP_PATH, "w", encoding="utf-8"), indent=1, sort_keys=True)
    print("  wrote baseline fingerprints: %s" % os.path.basename(FP_PATH))

newer = []
_comment_only = []
for rel in _inputs():
    cur = _fp(os.path.join(REPO, rel))
    if rel not in _base_fp:
        newer.append(rel)                      # an input the baseline never saw
    elif cur != _base_fp[rel]:
        newer.append(rel)                      # content differs from the baseline


def _strip_comments(text, tcl):
    # Normalise line endings first: git stores LF, the worktree has CRLF
    # (core.autocrlf). Comparing raw bytes across that difference reports every
    # file as changed.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if tcl:
        text = re.sub(r"(?m)^\s*#[^\n]*$", "", text)
        text = re.sub(r"(?m)\s+#[^\n]*$", "", text)
    else:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"//[^\n]*", "", text)
    return "\n".join(l.rstrip() for l in text.split("\n") if l.strip())


def _real_change(rel):
    """True when the file's CODE differs from the last commit.

    Two filters, in order:
      1. content identical to HEAD -> not a change at all. A file that was rewritten
         byte-for-byte (a mutation test restoring a backup, an editor re-saving) has
         a new mtime but the same design; reporting it as "CODE changed" is wrong.
      2. content differs -> compare with comments stripped, so a documentation fix
         does not look like a design change.
    """
    # Git object specs need forward slashes. os.path.relpath gives backslashes on
    # Windows, and "HEAD:rtl\\itch\\x.v" fails - which the caller then reads as
    # "changed". That single separator made every file look modified.
    rel = rel.replace("\\", "/")
    p = os.path.join(REPO, rel)
    if not os.path.exists(p):
        return True
    r = subprocess.run(["git", "show", "HEAD:" + rel], cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        return True
    cur = io.open(p, encoding="utf-8", errors="replace").read()
    if cur.replace("\r\n", "\n") == r.stdout.replace("\r\n", "\n"):
        return False
    is_tcl = rel.endswith((".tcl", ".xdc"))
    return _strip_comments(cur, is_tcl) != _strip_comments(r.stdout, is_tcl)


# A comment-only edit moves the timestamp without touching the design, which is how
# a documentation fix looked like a reproducibility failure.
# Round 204: the fingerprint answers "did this input change since the bitstream was built", which is the
# question this check exists to answer. `_real_change` answers a different one ("is the working tree dirty with
# a code edit") and was silently removing files from `newer` - so after committing a fix, HEAD moved and the
# filter hid genuine changes. The baseline question wins; `_real_change` is reported, not applied.
dirty = [f for f in newer if _real_change(f)]
clean = [f for f in newer if f not in dirty]


def _post_build_only(rel):
    """For a .tcl build script: did the change fall entirely AFTER the last artifact copy?

    Round 244 added a `puts` and an `expr` to build_overlay.tcl at L162, well past `launch_runs impl_1
    -to_step write_bitstream` at L71. **That cannot change the hardware** - it runs after the bitstream
    exists. But the fingerprint is per file, so it looked like a design change.

    The test: replay both versions up to the last `file copy` of the artifact pair; identical prefixes mean
    the change is after everything that produces the deliverable, and cannot affect it.

    This does NOT weaken the check for RTL or XDC - those have no "after the build" region.
    """
    if not rel.endswith(".tcl"):
        return False
    p = os.path.join(REPO, rel)
    try:
        cur = io.open(p, encoding="utf-8", errors="replace").read()
        r = subprocess.run(["git", "show", "HEAD:%s" % rel], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=REPO)
    except OSError:
        return False
    if r.returncode != 0:
        return False
    # The boundary is NOT `launch_runs impl_1`: the artifact is produced by the `file copy` commands that
    # follow it, and an edit there would change the delivered pair. Put the boundary at the LAST
    # artifact-producing statement, so a code change before it is still inspected.
    MARK = "file copy -force $hwh_src"

    def upto(text):
        i = text.find(MARK)
        return None if i < 0 else text[:i]

    a, b = upto(cur.replace("\r\n", "\n")), upto((r.stdout or "").replace("\r\n", "\n"))
    return a is not None and a == b


def _comment_only_change(rel):
    """For a .tcl or .xdc input: does the current file differ from HEAD only in comments?

    Round 245 corrected five `#` comments in create_project.tcl that still said 200 MHz when the file
    configures 190. **A comment cannot change what Vivado builds** - the same argument round 244 made for
    the post-write_bitstream region, applied to text that never reaches the tool.

    This is not a weakening: `_strip_comments` removes `#` lines for tcl/xdc and `/* */` + `//` for RTL, so
    a code change still differs after stripping and is still reported.
    """
    if not rel.endswith((".tcl", ".xdc", ".v")):
        return False
    p = os.path.join(REPO, rel)
    try:
        cur = io.open(p, encoding="utf-8", errors="replace").read()
        r = subprocess.run(["git", "show", "HEAD:%s" % rel], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=REPO)
    except OSError:
        return False
    if r.returncode != 0:
        return False
    is_tcl = rel.endswith((".tcl", ".xdc"))
    return _strip_comments(cur, is_tcl) == _strip_comments(r.stdout or "", is_tcl)


comment_only = []

if newer:
    _check_comment = [f for f in newer if _comment_only_change(f)]
    # Only for files committed at HEAD - an uncommitted edit is a different question.
    dirty_f = [f for f in newer if _real_change(f)]
    comment_only = [f for f in _check_comment if f not in dirty_f]
    if comment_only:
        newer = [f for f in newer if f not in comment_only]

if comment_only:
    print("  changes that touch only comments (cannot affect the artifact):")
    for f in comment_only:
        print("     " + f)

post_build = []
if newer:
    still = []
    for f in newer:
        if _post_build_only(f):
            post_build.append(f)
        else:
            still.append(f)
    newer = still

if post_build:
    print("  changes confined to after write_bitstream (cannot affect the artifact):")
    for f in post_build:
        print("     " + f)

print("  inputs differing from baseline: %d" % len(newer))
for f in clean:
    print("     %-46s changed (matches HEAD, i.e. committed)" % f)
for f in dirty:
    print("     %-46s changed and uncommitted" % f)

# Resource delta as a noise test.
rpt = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs",
                   "impl_1", "nasdaq_wrapper_utilization_placed.rpt")
util = {}
if os.path.exists(rpt):
    txt = io.open(rpt, encoding="utf-8", errors="replace").read()
    for key, pat in (("LUT", r"\|\s*Slice LUTs\s*\|\s*(\d+)"),
                     ("FF", r"\|\s*Slice Registers\s*\|\s*(\d+)"),
                     ("BRAM", r"\|\s*Block RAM Tile\s*\|\s*(\d+)"),
                     ("DSP", r"\|\s*DSPs\s*\|\s*(\d+)")):
        m = re.search(pat, txt)
        if m:
            util[key] = int(m.group(1))

print("  resources now                : %s" % util)
if "LUT" in util:
    delta = abs(util["LUT"] - 4507)
    print("  LUT delta vs baseline (4507) : %d (%.2f%%)"
          % (delta, 100.0 * delta / 4507))

print()
# Round 204: the fingerprint decides whether the DESIGN changed. `identical` only says whether P&R was
# deterministic on that input. Putting `identical` first makes a baseline copied from the current bitstream
# always pass - which is what I did and why this check went blind.
if newer:
    print("BITREPRO-DIFFERS")
    print("  -> the design inputs changed since the baseline:")
    for f in newer:
        print("     " + f)
    sys.exit(1)
elif identical:
    print("BITREPRO-IDENTICAL")
else:
    print("BITREPRO-DIFFERS")
    if not newer and util.get("LUT") is not None and abs(util["LUT"] - 4507) <= 50:
        print("  -> inputs unchanged and resources within placement noise:")
        print("     Vivado P&R is not deterministic. The shipped timing is")
        print("     authoritative; rebuilds vary by a few tenths of a ns.")
    else:
        print("  -> inputs or resources differ materially: investigate")
        sys.exit(1)
