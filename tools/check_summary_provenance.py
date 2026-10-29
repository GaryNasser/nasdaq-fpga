"""A board number in the summary must carry its build.

Round 37 established that every board figure came from one bitstream; round 48 added a
three-column reproducibility table; round 47 caught the summary quoting an older build's
WNS. Each fix was local to one figure.

The general rule: the opening summary must state which build produced the hardware numbers
it quotes. This check asserts that, and deliberately does NOT try to label each figure as
board or simulation - that judgement needs the sentence, not a character window, and four
attempts to automate it all produced the same answer while adding bugs.
"""
import io
import os
import re
import sys

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(REPORT):
    print("SUMMARY-PROVENANCE-FAIL (no report)")
    sys.exit(1)

lines = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read().split("\n")
# Round 27: a fixed 45-line window cut the summary short once two lines were added to it. Take
# the opening blockquote in full, but never fewer than 45 lines.
# Round 28: the window used to run past blank lines, so padding the document between the summary and
# the body pulled body content INTO the window. It ends at the first non-blank line after the minimum
# that is not part of the blockquote.
_n = 0
_seen_content = False
for _line in lines:
    if _line.strip():
        _seen_content = True
    if _n >= 45 and _seen_content and not _line.lstrip().startswith(">"):
        break
    _n += 1
head = lines[:_n]
print("summary window: %d line(s)" % _n)

BOARD_CLAIM = re.compile(
    r"板上已?实测|已经?上板|实拍[^\n]{0,10}回放|P50\s*\*?\*?\d|WNS\s*\*?\*?\+?0\.\d+")
# Round 27: the marker used to be two hard-coded hashes. Those are historical; the report now names
# 0BF5C1B0 and 62569926, and the check was comparing today's report against yesterday's builds.
#
# A marker is meaningful only if a build can be found for it: either the currently deployed pair, or any
# bitstream whose hash is recorded in the build archive.
def _known_builds():
    """The deployed bitstream's hash prefix, plus every prefix the report itself calls a build."""
    known = set()
    # Round 28: the LIVE artefact only. Walking the whole tree let any archived copy count, and the
    # report quotes builds that no longer exist - accepting those as proof defeats the check.
    import hashlib
    live = os.path.join(os.path.dirname(os.path.dirname(REPORT)), "vivado", "out", "nasdaq.bit")
    if os.path.exists(live):
        h = hashlib.md5(io.open(live, "rb").read()).hexdigest().upper()
        known.add(h[:8])
        known.add(h[:6])
    return known


_HASHES = _known_builds()

# Round 27: build the alternatives explicitly. The earlier one-liner mixed `+` with a conditional
# expression and produced a pattern the control-character audit rejected as unable to match text.
# Only hashes the tree can produce, plus the two prose markers. An earlier version also accepted
# `\b[0-9A-F]{8}…` - any eight hex digits - and `mutate_summary_prov` showed why that fails: stripping
# the real build still left other hashes matching, so the mutation was MISSED.
_ALTS = ["已上板 bitstream", "当前源码构建"]
_ALTS.extend(re.escape(h) for h in sorted(_HASHES))
BUILD_MARKER = re.compile("|".join(_ALTS))

print("build markers known: %d" % len(_HASHES))

print("board claims and build markers in the opening summary")
print()

claims = [i for i, l in enumerate(head, 1) if BOARD_CLAIM.search(l)]
markers = [i for i, l in enumerate(head, 1) if BUILD_MARKER.search(l)]

for i in claims:
    print("  claim  L%-4d %s" % (i, head[i - 1].strip()[:88]))
for i in markers:
    print("  build  L%-4d %s" % (i, head[i - 1].strip()[:88]))

print()
print("  %d board claim(s), %d build marker(s)" % (len(claims), len(markers)))

fails = []
if not claims:
    fails.append("no board claim found in the summary - the scan would be vacuous")
if not markers:
    fails.append("the summary asserts board results but never names the build")
if claims and markers:
    # A marker must sit near the first and the last claim, so neither end of the summary
    # quotes hardware results detached from their provenance.
    for label, idx in (("first", claims[0]), ("last", claims[-1])):
        if not any(abs(m - idx) <= 12 for m in markers):
            fails.append("the %s board claim (L%d) has no build marker within 12 lines"
                         % (label, idx))

print()
if fails:
    print("SUMMARY-PROVENANCE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("SUMMARY-PROVENANCE-PASS (%d claim(s); the summary names its build)"
      % len(claims))
