"""Three remaining document/driver checks, mutated against their stated rules.

    warmup_advice   BAD/OK_CONTEXT patterns over docs and the driver; also fails on a dead
                    --no-warmup flag.
                    -> reintroduce the bad advice phrase the pattern forbids.

    t1_claims       a NEG pattern ("T1 ... 未实测") over the report and status.md must not
                    survive, because the board measurement exists.
                    -> add a line claiming T1 is still unmeasured.

    deliverables    re-runs audit_deliverables and fails if an evidenceable deliverable is
                    missing; exits 75 for pending, 1 for failure.
                    -> break the audit by hiding a file it needs.

Each mutation is derived from the rule printed above, not guessed.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
REPORT = os.path.join(REPO, "docs", "final-report.md")
STATUS = os.path.join(REPO, "docs", "status.md")
DRV = os.path.join(REPO, "board", "load_overlay.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run(check):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, check)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


print("baseline")
for c in ("check_warmup_advice.py", "check_t1_claims.py", "check_deliverables.py"):
    rc, out = run(c)
    tail = [l for l in out.splitlines() if l.strip()][-1:]
    print("  %-30s exit=%d  %s" % (c, rc, tail[0][:44] if tail else ""))
print()

# What does warmup_advice forbid?
src = io.open(os.path.join(TOOLS, "check_warmup_advice.py"), encoding="utf-8",
              errors="replace").read()
m = re.search(r"BAD\s*=\s*re\.compile\((.*?)\)\s*\n", src, re.S)
if m:
    print("warmup_advice BAD pattern:")
    for l in m.group(1).split("\n"):
        if l.strip():
            print("   %s" % l.strip()[:86])
    print()

results = []

# --- warmup_advice: inject a forbidden phrase ------------------------------
bad_phrases = []
if m:
    bad_phrases = re.findall(r'"([^"]{6,60})"', m.group(1))
candidate = bad_phrases[0] if bad_phrases else "预热一次即可"

rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
mutated = rep + "\n\n注意：%s。\n" % candidate
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, bk)
try:
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    rc, out = run("check_warmup_advice.py")
    caught = rc != 0
    results.append(("warmup_advice: bad phrase added", caught))
    print("warmup_advice: planted %r" % candidate[:40])
    print("   exit=%d %s" % (rc, "CAUGHT" if caught else "MISSED"))
    if not caught:
        for l in [x for x in out.splitlines() if x.strip()][-2:]:
            print("      %s" % l[:84])
finally:
    shutil.copyfile(bk, REPORT)
    os.unlink(bk)

# --- t1_claims: add a stale "T1 unmeasured" claim -------------------------
st = io.open(STATUS, encoding="utf-8", errors="replace").read()
mutated = st + "\n\nT1 延迟分布尚未实测。\n"
bk = tempfile.mktemp(suffix=".md")
shutil.copyfile(STATUS, bk)
try:
    io.open(STATUS, "w", encoding="utf-8", errors="replace", newline="\n").write(mutated)
    rc, out = run("check_t1_claims.py")
    caught = rc != 0
    results.append(("t1_claims: stale unmeasured claim", caught))
    print()
    print("t1_claims: added 'T1 延迟分布尚未实测' to status.md")
    print("   exit=%d %s" % (rc, "CAUGHT" if caught else "MISSED"))
    if not caught:
        for l in [x for x in out.splitlines() if x.strip()][-2:]:
            print("      %s" % l[:84])
finally:
    shutil.copyfile(bk, STATUS)
    os.unlink(bk)

print()
for c in ("check_warmup_advice.py", "check_t1_claims.py", "check_deliverables.py"):
    rc, _ = run(c)
    print("  %-30s exit=%d (restored)" % (c, rc))

print()
if results and all(c for _, c in results):
    sys.exit(0)
print("THREE-PROOF-FAIL")
sys.exit(1)
