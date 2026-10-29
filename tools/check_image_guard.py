"""Fail if the simulation runner reuses a stale img.hex, or survives its absence.

Two properties, both about the image the three realfile-dependent suites need:

  1. REGENERATE  every run. The old code generated it only when the TEMP copy was absent,
                 so an image left by a previous session was silently reused even after the
                 capture changed. That is the staleness the provenance work fixed for
                 bitstreams, unfixed here.

  2. FAIL FAST   when generation fails. Previously the runner printed FAILED and continued,
                 so a missing dataset surfaced as three unrelated suite failures.

This is a static check (fast, runs in the suite): it reads run_sims.py and asserts the
structure. The behavioural counterpart, tools/test_image_fatal.py, runs a full simulation
and is kept out of the default suite.
"""
import io
import os
import re
import sys

P = r"D:\agent\nasdaq-fpga\tools\run_sims.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(P):
    print("IMAGE-GUARD-FAIL (run_sims.py not found)")
    sys.exit(1)

src = io.open(P, encoding="utf-8").read()
code = re.sub(r"#[^\n]*", "", src)

print("simulation runner, image handling")
print()

fails = []

# 1. build_image must be called unconditionally.
guarded = re.search(r"if\s+not\s+os\.path\.exists\(src_img\)\s*:\s*\n\s*(ok,\s*out\s*=\s*"
                    r"build_image\(\))", code)
calls = len(re.findall(r"build_image\(\)", code))
print("  build_image() calls        : %d" % calls)
print("  called under an exists() guard: %s" % bool(guarded))
if guarded:
    fails.append("build_image() is still conditional on the TEMP copy being absent, so a "
                 "stale img.hex can be reused")
if calls < 1:
    fails.append("build_image() is never called")

# 2. A failed build must exit.
fail_exit = re.search(r"if\s+not\s+ok[^\n]*:\s*\n(?:.*\n){0,12}?\s*sys\.exit\(1\)", code)
print("  exits on build failure     : %s" % bool(fail_exit))
if not fail_exit:
    fails.append("a failed image build does not stop the run")

# 3. The failure must name the token the suite reports.
token = "SIMSUITE-FAIL (no test image)" in src
print("  names SIMSUITE-FAIL        : %s" % token)
if not token:
    fails.append("the failure path does not emit a recognisable suite verdict")

# 4. It should point at the data file and the recipe.
names_data = "itch_loc6836.mold64" in src
points = "section 9.2" in src
print("  names the missing capture  : %s" % names_data)
print("  points at the recipe       : %s" % points)
if not names_data:
    fails.append("the failure message does not name the missing data file")

print()
if fails:
    print("IMAGE-GUARD-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("IMAGE-GUARD-PASS (image is regenerated every run and its failure is fatal)")
