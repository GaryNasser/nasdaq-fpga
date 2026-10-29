"""Fail if the recorded build inputs no longer match the working tree.

The provenance record now holds, for each RTL file and each build script, an md5 over the
code with comments and whitespace removed. That answers one question cleanly:

    does impl_1's artifact correspond to the sources as they stand?

If every fingerprint matches, the artifact is current. If any differs, something changed
since the recorded build and the artifact should not be quoted as describing the tree.

This is a comparison, cheap and exact - the alternative has been to reason from git
timestamps, which cost several rounds (30, 33, 36, 37, 47, 48).

It does NOT claim the bitstream can be reproduced byte-for-byte: Vivado P&R is not
deterministic and the report says so. It claims the INPUTS are the ones recorded.

Skips cleanly when provenance has no fingerprint section, which is the state of any
artifact built before this record existed.
"""
import hashlib
import io
import json
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
PROV = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1",
                    "BUILD-PROVENANCE.json")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def verilog_code_md5(path):
    raw = io.open(path, encoding="latin-1").read()
    code = re.sub(r"//[^\n]*", "", raw)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return hashlib.md5(re.sub(r"\s+", "", code).encode()).hexdigest()


def tcl_code_md5(path):
    raw = io.open(path, encoding="utf-8", errors="replace").read()
    out = []
    depth = 0
    for line in raw.split("\n"):
        s = line
        if depth == 0:
            if re.match(r"^\s*#", s):
                s = ""
            else:
                d = 0
                for i, ch in enumerate(s):
                    if ch == "{":
                        d += 1
                    elif ch == "}":
                        d = max(0, d - 1)
                    elif ch == "#" and d == 0 and i > 0 and s[i - 1] in " \t":
                        s = s[:i]
                        break
        depth = max(0, depth + s.count("{") - s.count("}"))
        out.append(s)
    return hashlib.md5(re.sub(r"\s+", "", "\n".join(out)).encode()).hexdigest()


if not os.path.exists(PROV):
    # Not a skip: an artifact with no record cannot be attributed to any source. Round 163 found a
    # rebuild had deleted this file and the check reported SKIPPED, which the suite counted as passing -
    # the same silent-pass shape as rounds 166-167.
    #
    # tools/gen_provenance.py regenerates it; a build that forgets to call it should fail here.
    print("PROVENANCE-CURRENT-FAIL (impl_1 has no BUILD-PROVENANCE.json)")
    print("  the artifact cannot be attributed to any source; run tools/gen_provenance.py")
    sys.exit(1)

rec = json.load(io.open(PROV, encoding="utf-8"))
srcs = rec.get("sources")
if not srcs:
    print("PROVENANCE-CURRENT-SKIPPED (record predates input fingerprints) - a SKIP, not a pass")
    sys.exit(2)

print("does impl_1's artifact correspond to the current sources?")
print()
print("  bitstream: %s" % rec.get("bitstream_md5", "?")[:16])
print()

fails = []
checked = 0
for rel, info in sorted(srcs.items()):
    p = os.path.join(REPO, rel)
    if not os.path.exists(p):
        print("  %-30s *** FILE MISSING ***" % rel)
        fails.append("%s is recorded but no longer exists" % rel)
        continue
    want = info.get("code_md5", "")
    # Dispatch on the RECORDED rule, not on a guessed extension: .xdc is Tcl, and
    # rel.endswith(".tcl") is False for it. Earlier this mis-hashed the XDC as Verilog
    # and reported a spurious change.
    rule = info.get("rule") or ("verilog" if rel.endswith(".v") else "tcl")
    got = verilog_code_md5(p) if rule == "verilog" else tcl_code_md5(p)
    checked += 1
    same = (got == want)
    print("  %-30s %s %s" % (rel, "match" if same else "DIFFERS",
                             "" if same else "(%s -> %s)" % (want[:10], got[:10])))
    if not same:
        fails.append("%s changed since the recorded build" % rel)

print()
if checked == 0:
    print("PROVENANCE-CURRENT-FAIL (no inputs compared)")
    sys.exit(1)

if fails:
    print("PROVENANCE-CURRENT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    print()
    print("  The artifact in impl_1 predates a source change. Either rebuild, or")
    print("  stop quoting this artifact as describing the current tree.")
    sys.exit(1)

print("PROVENANCE-CURRENT-PASS (%d inputs match the recorded build)" % checked)
