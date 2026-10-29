"""Mutations for the build-pairing check.

  1. point wns_value back at build_check/rebuild.log  -> the forbidden file is used again
  2. break the provenance MD5                          -> provenance does not match the .bit
  3. touch the timing report far from the bitstream    -> different run

Each restores afterwards, and the healthy path must pass.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = r"D:\agent\nasdaq-fpga"
AUDIT = os.path.join(REPO, "tools", "audit_deliverables.py")
PROV = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1",
                    "BUILD-PROVENANCE.json")
CHECK = os.path.join(REPO, "tools", "check_build_pairing2.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ab = tempfile.mktemp(suffix=".py")
shutil.copyfile(AUDIT, ab)
original = io.open(AUDIT, encoding="utf-8").read()

results = []

# 1. use the forbidden log again
m1 = original.replace(
    't = read("vivado/workspace/nasdaq/nasdaq.runs/impl_1/"\n'
    '             "nasdaq_wrapper_timing_summary_routed.rpt")',
    't = read("build_check/rebuild.log")', 1)
if m1 == original:
    # the string may be formatted differently; do a targeted substitution
    m1 = original.replace('"nasdaq_wrapper_timing_summary_routed.rpt")',
                          '"nasdaq_wrapper_timing_summary_routed.rpt") or read("build_check/rebuild.log")', 1)
if m1 != original:
    io.open(AUDIT, "w", encoding="utf-8", newline="\n").write(m1)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    results.append(("use rebuild.log again", True, r.returncode != 0))
    print("%-28s landed=True  exit=%d %s"
          % ("use rebuild.log again", r.returncode,
             "CAUGHT" if r.returncode else "MISSED"))
    io.open(AUDIT, "w", encoding="utf-8", newline="\n").write(original)

# 2. break the provenance MD5
pb = tempfile.mktemp(suffix=".json")
if os.path.exists(PROV):
    shutil.copyfile(PROV, pb)
    raw = io.open(PROV, encoding="utf-8").read()
    # Round 250: the old hardcoded prefix 0ADD0828 was a superseded build, so the replacement never happened
    # and this mutation reported a verdict about nothing. Take the CURRENT md5 and flip its first 8 chars.
    import json as _json
    _cur = str(_json.loads(raw).get("bitstream_md5", ""))[:8]
    if not _cur:
        print("%-28s INCONCLUSIVE (no bitstream_md5 in provenance)" % "provenance MD5 broken")
        results.append(("provenance MD5 broken", False, False))
    else:
        _new = raw.replace(_cur, "DEADBEEF" if _cur != "DEADBEEF" else "0BADF00D", 1)
        io.open(PROV, "w", encoding="utf-8", newline="\n").write(_new)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    results.append(("provenance MD5 broken", True, r.returncode != 0))
    print("%-28s landed=True  exit=%d %s"
          % ("provenance MD5 broken", r.returncode,
             "CAUGHT" if r.returncode else "MISSED"))
    shutil.copyfile(pb, PROV)
    os.unlink(pb)

# 3. move the timing report's mtime far from the bitstream
TIM = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1",
                   "nasdaq_wrapper_timing_summary_routed.rpt")
if os.path.exists(TIM):
    old = os.path.getmtime(TIM)
    os.utime(TIM, (old - 7200, old - 7200))
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    results.append(("timing report from another run", True, r.returncode != 0))
    print("%-28s landed=True  exit=%d %s"
          % ("timing report from another run", r.returncode,
             "CAUGHT" if r.returncode else "MISSED"))
    os.utime(TIM, (old, old))

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(ab, AUDIT)
os.unlink(ab)

print()
ok = len(results) == 3 and all(c for _, l, c in results) and r.returncode == 0
print("BUILD-PAIRING-MUTATION-PASS" if ok else "BUILD-PAIRING-MUTATION-FAIL")
sys.exit(0 if ok else 1)
