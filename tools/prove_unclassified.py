"""My proof was wrong, not the check.

`check_unclassified_guards` reads each guard's source (L42) and asks one question: **does the guard's
SKIPPED/FAIL verdict match the kind of thing it protects?** A build script must FAIL; a build artifact must SKIP.

I retargeted `create_project.tcl` to a different filename. That changes which file is protected, not whether the
guard skips or fails - so the verdict was still consistent and the check rightly passed.

**The right mutation flips the verdict**: turn `check_cdc_map.py`'s FAIL into a SKIPPED-with-exit(0), which is
exactly the regression (a build-script guard reverting to a silent skip).
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_unclassified_guards.py")
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("what the check reads: the guard's printed verdict, not its target")
print()

CASES = [
    ("check_cdc_map.py", "build script", "FAIL", "SKIPPED", "2", "0"),
    ("check_provenance_current.py", "build artifact", "SKIPPED", "FAIL", "2", "1"),
]

results = []


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=TOOLS, timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


for fname, label, from_word, to_word, from_code, to_code in CASES:
    path = os.path.join(TOOLS, fname)
    if not os.path.exists(path):
        print("  %-30s missing" % fname)
        continue
    body = io.open(path, encoding="utf-8", errors="surrogateescape").read()

    # Find the guarded print+exit pair this check matches.
    m = re.search(r"(print\(\s*[\"'][A-Z0-9\-]*)(SKIPPED|FAIL)([^\"']*[\"'][^)]*\)\s*\n\s*sys\.exit\()(\d)",
                  body)
    if not m:
        print("  %-30s no guard found" % fname)
        continue

    bk = tempfile.mktemp(suffix=".py")
    shutil.copyfile(path, bk)
    try:
        mutated = body[:m.start()] + m.group(1) + to_word + m.group(3) + to_code + body[m.end():]
        io.open(path, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        results.append((label, caught))
        print("  %-16s flip %s->%s   exit=%d %s" % (label, from_word, to_word, rc,
                                                    "CAUGHT" if caught else "MISSED"))
    finally:
        shutil.copyfile(bk, path)
        os.unlink(bk)

rc2, _ = run()
print()
print("restored: exit=%d" % rc2)

caught_n = sum(1 for _, c in results if c)
print()
if results and caught_n == len(results) and rc2 == 0:
    print("UNCLASSIFIED-PROOF-PASS (%d/%d verdict flips caught)" % (caught_n, len(results)))
    sys.exit(0)
print("UNCLASSIFIED-PROOF-FAIL (%d of %d caught)" % (caught_n, len(results)))
sys.exit(1)
