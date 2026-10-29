"""Prove check_deploy_triple fails when the provenance no longer matches the bitstream.

The check asserts three-way consistency: `bit` traces to `BUILD-PROVENANCE.json`, `hwh` matches the BD handoff, and
both files exist. **None of that had a proof** - if the comparison were inverted or skipped, the check would still
print its PASS line.

### The mutation, chosen to be the real failure

Corrupt the provenance JSON's recorded MD5. The bitstream stays valid; only the claim about it becomes false. That
is exactly what a stale or hand-edited provenance looks like.

The proof must also confirm the check passes again once restored - otherwise it only shows the check can fail for
some reason, not for this one.
"""
import io
import json
import os
import shutil
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_deploy_triple.py")
PROV = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1",
                    "BUILD-PROVENANCE.json")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK))
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


if not os.path.exists(PROV):
    print("PROVENANCE-PROOF-FAIL (no provenance file to mutate)")
    sys.exit(1)

rc0, out0 = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("PROVENANCE-PROOF-FAIL (the check does not pass on the current tree)")
    sys.exit(1)

bk = PROV + ".bak"
shutil.copyfile(PROV, bk)
try:
    data = json.load(io.open(PROV, encoding="utf-8"))
    print("recorded md5: %s" % data.get("bitstream_md5"))

    # Flip one hex digit in the recorded hash.
    h = data["bitstream_md5"]
    flipped = h[:-1] + ("0" if h[-1] != "0" else "1")
    data["bitstream_md5"] = flipped
    json.dump(data, io.open(PROV, "w", encoding="utf-8"), indent=1, sort_keys=True)
    print("mutated to  : %s" % flipped)

    rc1, out1 = run()
    caught = rc1 != 0
    print("mutated : exit=%d %s" % (rc1, "CAUGHT" if caught else "MISSED"))
    if not caught:
        for l in [x for x in out1.split("\n") if x.strip()][-3:]:
            print("   " + l.strip()[:80])
finally:
    shutil.copyfile(bk, PROV)
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)

print()
if caught and rc2 == 0:
    print("PROVENANCE-PROOF-PASS (a corrupted provenance is caught and the restoration is clean)")
    sys.exit(0)
print("PROVENANCE-PROOF-FAIL (caught=%s, restored_clean=%s)" % (caught, rc2 == 0))
sys.exit(1)
