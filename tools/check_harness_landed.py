"""The harness-quality audit judged by keywords and produced four false alarms.

It searched for the words landed / == orig / NOT APPLIED, concluded four harnesses lacked a
landed-check, and would have had me add guards to code that did not need them.

Behavioural test: break each harness's anchors so its mutations cannot apply, and see if it
still exits 0. All four exit 1. They already verify that their mutations land - by comparing
the mutated text against the original, or by having no skip path at all.

So the audit measured a coding STYLE, not a property. Rewriting it to test the property:
a harness must not report success when its mutation cannot be applied.

The behavioural test needs a way to disable the mutation generically. The one that worked:
replace each long string literal in the harness source with a sentinel, which breaks whatever
anchor the harness searches for.

That is crude but it is exactly the fault being tested - "the anchor changed, so nothing
matched". A harness that survives it is the fault; one that fails is sound.
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
RC = os.path.join(TOOLS, "run_checks.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(RC, encoding="utf-8").read()
paths = dict((m.group(1), m.group(2))
             for m in re.finditer(r'"(\w+)":\s*"([\w.]+\.py)"', src))
suite = [m.group(1) for m in re.finditer(r'\("(\w+)",\s*"[^"]*",\s*\w+\)', src)]
harnesses = sorted(set(paths[n] for n in suite
                       if paths.get(n, "").startswith(("mutate_", "prove_"))))

print("harnesses: %d" % len(harnesses))
print()

bad = []
for h in harnesses:
    p = os.path.join(TOOLS, h)
    if not os.path.exists(p):
        print("  %-32s MISSING FROM DISK" % h)
        bad.append(h)
        continue
    text = io.open(p, encoding="utf-8", errors="replace").read()

    anchors = set(re.findall(r'(r?"[^"\n]{12,40}")', text))
    broken = text
    n = 0
    for a in anchors:
        if "\\n" in a or a.startswith('r""') or "REPO" in a:
            continue
        broken = broken.replace(a, a[0] + "ZZ_NEVER_MATCHES_ZZ" + a[-1], 1)
        n += 1
    if n == 0:
        print("  %-32s no anchor to break" % h)
        continue

    bk = tempfile.mktemp(suffix=".py")
    shutil.copyfile(p, bk)
    # Round 252: a finally-block does not run if the process is killed (suite timeout). Register an
    # atexit restore as well, so an interrupted run cannot leave the file broken on disk.
    import atexit
    _p_copy, _bk_copy = p, bk
    atexit.register(lambda _p=_p_copy, _b=_bk_copy: os.path.exists(_b) and shutil.copyfile(_b, _p))
    try:
        io.open(p, "w", encoding="utf-8", newline="\n").write(broken)
        try:
            r = subprocess.run([sys.executable, p], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
            rc = r.returncode
        except subprocess.TimeoutExpired:
            rc = -1
        ok = rc != 0
        print("  %-32s dead anchors -> exit=%-3d %s"
              % (h, rc, "fails (sound)" if ok else "PASSES (would prove nothing)"))
        if not ok:
            bad.append(h)
    finally:
        shutil.copyfile(bk, p)
        os.unlink(bk)

print()
if bad:
    print("HARNESS-LANDED-FAIL (%d)" % len(bad))
    for h in bad:
        print("  %s reports success without applying its mutation" % h)
    sys.exit(1)
print("HARNESS-LANDED-PASS (%d harnesses fail when their anchors cannot match)"
      % (len(harnesses) - len(bad)))
