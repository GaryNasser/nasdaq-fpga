"""Check that the shipped bitstream is newer than every RTL source it contains.

The bitstream is the artifact that runs on hardware. If any RTL file changed after
it was built, the artifact no longer represents the source, and the whole
verification story (which verifies the SOURCE) stops applying to what would be
loaded.

This is not hypothetical: rounds 65 and 83 both edited RTL after a build, and the
03:21 bitstream sat stale for over an hour while every test continued to pass -
because every test compiles from source, not from the bitstream.

A timestamp comparison is a crude proxy for "built from this source", but it
catches the common case (edited after building) without needing a build system.
"""
import io
import hashlib
import json
import os
import re
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
BIT = os.path.join(REPO, "vivado", "out", "nasdaq.bit")
HWH = os.path.join(REPO, "vivado", "out", "nasdaq.hwh")
RTL_DIR = os.path.join(REPO, "rtl")
PROV_JSON = os.path.join(REPO, "vivado", "workspace", "nasdaq",
                        "nasdaq.runs", "impl_1", "BUILD-PROVENANCE.json")

# Every RTL file that feeds the build.
def rtl_sources():
    out = []
    for root, _dirs, files in os.walk(RTL_DIR):
        for f in files:
            if f.endswith(".v") and not f.startswith("tb_"):
                out.append(os.path.join(root, f))
    return out


if not os.path.exists(BIT):
    print("bitstream missing: %s" % BIT)
    sys.exit(1)


def unchanged_vs_head(path):
    """True when the file's content equals its committed version.

    A newer mtime does not mean a newer DESIGN. Restoring a backup byte-for-byte, or an
    editor re-saving, moves the timestamp without changing the file - and then "the
    bitstream is older than its sources" is a false alarm (round 36 hit this twice).

    A COMMENT edit likewise cannot change the netlist, so comments are stripped before
    the comparison - the same rule check_bit_repro uses. A code edit of any size is
    still caught.
    """
    rel = os.path.relpath(path, REPO).replace("\\", "/")
    try:
        r = subprocess.run(["git", "show", "HEAD:" + rel], cwd=REPO,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    except OSError:
        return False
    if r.returncode != 0:
        return False
    try:
        cur = io.open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False

    def strip(s):
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
        s = re.sub(r"//[^\n]*", "", s)
        return "\n".join(l.rstrip() for l in s.split("\n") if l.strip())

    return strip(cur) == strip(r.stdout)


bit_mtime = os.path.getmtime(BIT)
srcs = rtl_sources()

# Decide by CONTENT against the recorded build inputs, not by timestamps.
#
# The old form took every file with a newer mtime as a candidate, then dropped the ones
# whose content matched git HEAD. That answers "edited since commit?", which is close to
# - but not the same as - "differs from what went into the bitstream?". The two coincide
# only while HEAD equals the build inputs.
#
# BUILD-PROVENANCE.json (round 58) records a comment-stripped code fingerprint per input
# at build time, which is exactly the baseline this check needs. Where a record exists it
# is authoritative; where it does not, the HEAD comparison remains the fallback.
_rec = {}
if os.path.exists(PROV_JSON):
    try:
        _rec = json.load(io.open(PROV_JSON, encoding="utf-8")).get("sources", {}) or {}
    except Exception:
        _rec = {}


def _code_md5(path):
    """Comment- and whitespace-stripped hash, matching how the record was made."""
    raw = io.open(path, encoding="latin-1", errors="replace").read()
    code = re.sub(r"//[^\n]*", "", raw)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return hashlib.md5(re.sub(r"\s+", "", code).encode()).hexdigest()


def differs_from_build(p):
    """True when p's content is not what the recorded build used.

    Falls back to the HEAD comparison when no record covers this file.
    """
    rel = os.path.relpath(p, REPO).replace(os.sep, "/")
    entry = _rec.get(rel)
    if entry and entry.get("code_md5"):
        return _code_md5(p) != entry["code_md5"]
    # No record: keep the previous behaviour.
    return not unchanged_vs_head(p)


newer = []
for p in srcs:
    if differs_from_build(p):
        newer.append((p, os.path.getmtime(p)))

if _rec:
    print("baseline   : recorded build inputs (content)")
else:
    print("baseline   : git HEAD (no build record)")

import datetime
print("bitstream  : %s" % datetime.datetime.fromtimestamp(bit_mtime))
print("hwh        : %s" % (datetime.datetime.fromtimestamp(os.path.getmtime(HWH))
                          if os.path.exists(HWH) else "(missing)"))
print("rtl sources: %d" % len(srcs))
print()


# The .hwh is written during synthesis, the .bit after implementation, so the hwh
# is legitimately older - but it must still postdate every RTL source, or it
# describes an older design than the bitstream it ships beside.
hwh_mtime = os.path.getmtime(HWH) if os.path.exists(HWH) else None
if hwh_mtime is not None:
    # Same content rule as the bitstream comparison above: a newer mtime with
    # unchanged code (or only comment changes) does not mean a newer design.
    hwh_newer = [(p, os.path.getmtime(p)) for p in srcs
                 if os.path.getmtime(p) > hwh_mtime
                 and not unchanged_vs_head(p)]
    print()
    if hwh_newer:
        print("STALE HWH - %d source(s) newer than the handoff:" % len(hwh_newer))
        for p, t in sorted(hwh_newer, key=lambda x: -x[1]):
            print("  %-42s %s" % (os.path.basename(p),
                                  datetime.datetime.fromtimestamp(t)))
        newer.extend([(p, t) for p, t in hwh_newer if (p, t) not in newer])
    else:
        print("handoff postdates every RTL source")
if newer:
    print("STALE - %d source file(s) newer than the bitstream:" % len(newer))
    for p, t in sorted(newer, key=lambda x: -x[1]):
        print("  %-42s %s" % (os.path.basename(p),
                              datetime.datetime.fromtimestamp(t)))
    print()
    print("ARCH-STALE")
    sys.exit(1)

print("every RTL source predates the bitstream")
print("ARCH-CURRENT")
