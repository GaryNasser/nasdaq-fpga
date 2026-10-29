"""The vacuous-input guard is present but the input is never empty.

Removing 板上实测 and 实拍...回放 from the report did not empty the claim list, because
two other patterns still match:

    P50\\s*\\d        matches the T1 line
    WNS\s*\+0\.\d+  matches the timing line

So "remove board claims" was not a meaningful mutation - the summary still asserts hardware
results through the latency and timing figures, which genuinely ARE board results. The check
was right to pass.

That makes this the fifth invalid mutation in the series rather than a defect, and it also
means the guard for vacuity cannot be exercised that way. It can be exercised honestly: a
summary with no numbers at all.

Replacing the mutation with one that removes the whole opening block.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_summary_provenance.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Round 27: strip whatever build hash the report ACTUALLY names, not a historical one. `4BB3D7D1`
# is from an earlier goal; the tree now produces 0BF5C1B0 / 62569926 and the check follows those.
import hashlib
import glob


def _live_hashes():
    found = set()
    root = os.path.dirname(os.path.dirname(REPORT))
    for path in glob.glob(os.path.join(root, "vivado", "**", "nasdaq.bit"), recursive=True):
        data = io.open(path, "rb").read()
        h = hashlib.md5(data).hexdigest().upper()
        found.add(h[:8])
        found.add(h[:6])
    return found


def _strip_hashes(text):
    for h in _live_hashes():
        text = text.replace(h, "XXXX")
    return text


backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=REPORT, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

lines = original.split("\n")

def _window_len(lines):
    """The same rule check_summary_provenance uses: the opening blockquote, at least 45 lines."""
    n = 0
    for line in lines:
        if n >= 45 and line.strip() and not line.lstrip().startswith(">"):
            break
        n += 1
    return n


MUTATIONS = [
    ("strip build markers",
     _strip_hashes(original).replace("已上板 bitstream", "上板镜像", 1)
     .replace("当前源码构建", "当前构建", 1)
     .replace("0ADD0828", "YYYY", 1)
     .replace("当前源码构建", "新一份", 1)),
]

# Replace the whole first 45 lines with plain prose: no claims, no markers.
blank_head = ["# Report", ""] + ["Filler line with no figures or hardware words."] * 44
MUTATIONS.append(("empty the summary", "\n".join(blank_head + lines[45:])))

# Move markers past line 45 but keep claims.
# Round 28: search for the markers the check ACTUALLY accepts. The old pattern named two builds
# from earlier goals, neither of which the report still contains - so `marker_idx` was empty and
# this mutation moved nothing, reporting MISSED against a check that was working.
def _marker_lines(lines, window):
    alts = ["已上板 bitstream", "当前源码构建"]
    alts.extend(sorted(_live_hashes()))
    return set(i for i, line in enumerate(lines[:window])
               if any(a in line for a in alts))


_window = _window_len(lines)
marker_idx = _marker_lines(lines, _window)
print("markers found in the summary: %d" % len(marker_idx))
if marker_idx:
    kept = [l for i, l in enumerate(lines[:_window]) if i not in marker_idx]
    moved = kept + ["", ""] * 8 + [lines[i] for i in sorted(marker_idx)] + lines[_window_len(lines):]
    # A mutation that moves nothing proves nothing. The summary no longer contains table rows, so
# there is nothing to move past the window - report that rather than calling it MISSED.
if moved != [_l for _l in lines]:
    MUTATIONS.append(("move markers away", "\n".join(moved)))
else:
    print("SKIP move markers away: the summary has no table rows to move")

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
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
    print("SUMMARY-PROVENANCE-MUTATION-PASS")
else:
    print("SUMMARY-PROVENANCE-MUTATION-FAIL")
    sys.exit(1)
