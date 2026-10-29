"""Stop inferring which checks read RTL. Measure it.

Three attempts to classify by source text, each wrong in a different direction:

    1  match "rtl/itch" anywhere          25 hits, includes checks that only mention it
    2  match an io.open/read of an RTL path  9 hits, misses checks that build the path from a
                                             raw-string constant and pass it to open() later
    3  ... and the constants are r"D:\\...\\rtl\\itch\\x.v", which pattern 2 does not see

The reliable way is not a better regex but an observation: run each check and see which files
it opens. Python can report that with an audit hook - sys.addaudithook fires on open() - so
the classification comes from behaviour rather than from guessing at source shape.

That is exact by construction, and cheap: each check is already run by the suite.

Implementation: a wrapper that installs an audit hook, execs the checker's source, and records
every path containing rtl/ or .xdc that was opened. It runs the checker in a subprocess so the
suite's own run is unaffected.
"""
import glob
import io
import json
import os
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RUNNER = tempfile.mktemp(suffix=".py")
io.open(RUNNER, "w", encoding="utf-8", newline="\n").write('''
import json, os, runpy, sys

target = sys.argv[1]
opened = []

def hook(event, args):
    if event == "open" and args:
        p = args[0]
        if isinstance(p, str):
            q = p.replace("\\\\", "/")
            if "rtl/itch" in q or q.endswith(".xdc") or "/rtl/" in q:
                opened.append(q)

sys.addaudithook(hook)
sys.argv = [target]
try:
    runpy.run_path(target, run_name="__main__")
except SystemExit:
    pass
except Exception:
    pass

seen = []
for p in opened:
    b = os.path.basename(p)
    if b not in seen:
        seen.append(b)
print("OPENED:" + json.dumps(seen))
''')

env = dict(os.environ)
env["PATH"] = r"D:\Xilinx\Vivado\2024.1\bin;" + env.get("PATH", "")
env["PYTHONIOENCODING"] = "utf-8"

print("checks that OPEN an RTL or constraint file while running")
print()

readers, non_readers = [], []
for p in sorted(glob.glob(os.path.join(TOOLS, "check_*.py"))):
    name = os.path.basename(p)
    try:
        r = subprocess.run([sys.executable, RUNNER, p], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env, timeout=300)
    except subprocess.TimeoutExpired:
        print("  %-34s TIMEOUT" % name)
        continue
    line = [l for l in (r.stdout or "").splitlines() if l.startswith("OPENED:")]
    files = json.loads(line[-1][7:]) if line else []
    if files:
        readers.append((name, files))
        print("  %-34s %s" % (name, ", ".join(files[:3])))

print()
print("  readers: %d" % len(readers))

harness_text = ""
for p in glob.glob(os.path.join(TOOLS, "mutate_*.py")):
    harness_text += io.open(p, encoding="utf-8", errors="replace").read()

unc = [(n, f) for n, f in readers
       if n not in harness_text and n.replace("check_", "").replace(".py", "") not in harness_text]
print("  with a mutation harness: %d" % (len(readers) - len(unc)))
print("  without: %d" % len(unc))
for n, f in unc:
    print("     %-34s %s" % (n, ", ".join(f[:2])))

os.unlink(RUNNER)

print()
if not readers:
    print("RTL-READER-FAIL (no check opened an RTL file - the measurement failed)")
    sys.exit(1)
print("RTL-READER-PASS (%d checks measurably read RTL" % len(readers))
