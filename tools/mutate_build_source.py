"""Mutations for the build-source check.

The check's claim: no checker treats a non-deployed build log as the shipped figure.

  1. make a checker read rebuild.log for WNS and compare it to the report  -> should FAIL
  2. corrupt experiment_mcyc.log's figures so it no longer matches impl_1   -> the log
     moves to "differing", and any checker relying on it without comparing fails
  3. delete impl_1's timing summary                                        -> no deployed
     reference exists, everything that reads a log becomes unverifiable
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHECK = os.path.join(REPO, "tools", "check_build_source.py")
VERIFY = os.path.join(REPO, "tools", "verify_util_branch.py")
IMPL = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1")
TIMING = os.path.join(IMPL, "nasdaq_wrapper_timing_summary_routed.rpt")
EXPERIMENT = os.path.join(REPO, "build_check", "experiment_mcyc.log")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

results = []

# Baseline
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("%-34s exit=%d (baseline)" % ("healthy", r.returncode))

# 1. A checker that uses rebuild.log as the shipped figure.
probe = os.path.join(REPO, "tools", "tmp_shipped_probe.py")
io.open(probe, "w", encoding="utf-8", newline="\n").write(
    'import io, re\n'
    't = io.open(r"D:\\agent\\nasdaq-fpga\\build_check\\rebuild.log",\n'
    '            encoding="utf-8", errors="replace").read()\n'
    'm = re.search(r"TIMING-METRICS: WNS=([-+]?\\d+\\.\\d+)", t)\n'
    'print("WNS", m.group(1))\n')
try:
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append(("a checker uses rebuild.log", caught))
    print("%-34s exit=%d %s" % ("a checker uses rebuild.log", r.returncode,
                                "CAUGHT" if caught else "MISSED"))
finally:
    os.remove(probe)

# 2. Corrupt experiment_mcyc.log so it no longer matches impl_1.
if os.path.exists(EXPERIMENT):
    bk = tempfile.mktemp(suffix=".log")
    shutil.copyfile(EXPERIMENT, bk)
    raw = io.open(EXPERIMENT, encoding="utf-8", errors="replace").read()
    io.open(EXPERIMENT, "w", encoding="utf-8", newline="\n").write(
        raw.replace("WNS=0.042 WHS=0.034", "WNS=0.099 WHS=0.011"))
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    moved = "experiment_mcyc.log" in out and "differing" in out
    results.append(("experiment log diverges", moved))
    print("%-34s exit=%d %s" % ("experiment log diverges", r.returncode,
                                "detected as differing" if moved else "not detected"))
    shutil.copyfile(bk, EXPERIMENT)
    os.unlink(bk)

# 3. Remove impl_1's timing summary.
if os.path.exists(TIMING):
    bk2 = tempfile.mktemp(suffix=".rpt")
    ORIG_MTIME = os.path.getmtime(TIMING)   # capture BEFORE copying; copyfile resets it
    shutil.copyfile(TIMING, bk2)
    os.remove(TIMING)
    try:
        r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        noted = "MISSING" in out
        results.append(("no deployed reference", noted))
        print("%-34s exit=%d %s" % ("no deployed reference", r.returncode,
                                    "reported missing" if noted else "NOT reported"))
    finally:
        # copyfile does not preserve mtime, and this file's mtime is exactly what the
        # build-pairing check tests. Restore it to its original value.
        shutil.copyfile(bk2, TIMING)
        os.utime(TIMING, (ORIG_MTIME, ORIG_MTIME))
        os.unlink(bk2)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("%-34s exit=%d (restored)" % ("healthy", r.returncode))

print()
ok = (len(results) == 3 and all(c for _, c in results) and r.returncode == 0)
print("BUILD-SOURCE-MUTATION-PASS" if ok else "BUILD-SOURCE-MUTATION-FAIL")
sys.exit(0 if ok else 1)
