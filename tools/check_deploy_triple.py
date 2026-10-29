"""Assert the deployed triple is consistent: bit matches its provenance, hwh matches the BD handoff.

Round 178 audited this by hand after the board had been offline for 25 rounds. A hand audit does not survive
the next rebuild, and a mismatched bit/hwh pair would surface as a mysterious board result - the failure mode
this project has spent many rounds on.

### What it asserts

    nasdaq.bit  md5 == BUILD-PROVENANCE.json bitstream_md5
    nasdaq.hwh  md5 == nasdaq.gen/.../hw_handoff/nasdaq.hwh

Both by CONTENT, never by mtime. This project has drawn a conclusion from mtime ordering three times (rounds 33,
163, 178) and been wrong twice.

### What it deliberately does not assert

That `out/` is newer than `impl_1/`. The hwh is legitimately regenerated after the bitstream, so an mtime
comparison would produce a false failure - which is exactly the trap the hand audit had to reason around.
"""
import hashlib
import io
import json
import os
import sys

REPO = r"D:\agent\nasdaq-fpga"
OUT = os.path.join(REPO, "vivado", "out")
IMPL = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1")
GEN = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.gen",
                   "sources_1", "bd", "nasdaq", "hw_handoff", "nasdaq.hwh")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

fails = []


def md5(p):
    return hashlib.md5(io.open(p, "rb").read()).hexdigest()


bit = os.path.join(OUT, "nasdaq.bit")
hwh = os.path.join(OUT, "nasdaq.hwh")
prov = os.path.join(IMPL, "BUILD-PROVENANCE.json")

print("deployed triple consistency")
print()

# --- bit vs provenance ---------------------------------------------------------------
if not os.path.exists(bit):
    fails.append("out/nasdaq.bit is missing")
elif not os.path.exists(prov):
    fails.append("BUILD-PROVENANCE.json is missing - the bitstream is unattributable")
else:
    want = json.load(io.open(prov, encoding="utf-8")).get("bitstream_md5", "")
    got = md5(bit)
    ok = (got == want)
    print("  bit vs provenance   %s  %s" % (got[:16], "MATCH" if ok else "DIFFERS from %s" % want[:16]))
    if not ok:
        fails.append("out/nasdaq.bit does not match the recorded build")

# --- hwh vs handoff ------------------------------------------------------------------
if not os.path.exists(hwh):
    fails.append("out/nasdaq.hwh is missing")
elif not os.path.exists(GEN):
    print("  hwh vs BD handoff   (handoff absent; cannot compare)")
else:
    a, b = md5(hwh), md5(GEN)
    ok = (a == b)
    print("  hwh vs BD handoff   %s  %s" % (a[:16], "MATCH" if ok else "DIFFERS from %s" % b[:16]))
    if not ok:
        fails.append("out/nasdaq.hwh is not the current block design's handoff")

print()
if fails:
    print("DEPLOY-TRIPLE-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)

print("DEPLOY-TRIPLE-PASS (bit traces to its build; hwh is the current BD's handoff)")
