"""make_realfile must honour REALFILE_SRC - this round's own experiment was invalid without it.

    SRC = r"D:\\agent\\nasdaq-fpga\\data\\itch_loc6836.mold64"     (before)
    SRC = os.environ.get("REALFILE_SRC") or r"..."                 (now)

The first attempt at the corrupted-session experiment patched run_realfile.py and set an
environment variable. The variable reached run_realfile but not make_realfile, which run_realfile
calls to build the image - so the testbench loaded the ORIGINAL capture and the run was the
normal one. It reported 850/850 and err=0, and that was correct for the input it actually saw.

The check: generate an image from a sentinel file and confirm the first byte of img.hex is the
sentinel. That is exactly the link that was broken.
"""
import io
import os
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
GEN = os.path.join(REPO, "tools", "make_realfile.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(GEN, encoding="utf-8").read()
print("make_realfile's source selection")
print()
for l in src.split("\n")[:16]:
    if "SRC" in l or "environ" in l:
        print("  %s" % l.strip()[:88])

if "REALFILE_SRC" not in src:
    print()
    print("REALFILE-SRC-FAIL (make_realfile ignores REALFILE_SRC)")
    print("  an experiment driving a modified capture would silently use the original")
    sys.exit(1)

# Build a sentinel capture: valid MoldUDP64 header with a distinctive first byte.
sentinel = os.path.join(tempfile.gettempdir(), "nasdaq_sentinel.mold64")
body = bytearray(b"ZZZZZZZZ")          # 8-byte session, deliberately invalid
body += bytes([0x00, 0x01])            # seq 1
body += bytes([0x00, 0x00])            # count 0
open(sentinel, "wb").write(bytes(body))

env = dict(os.environ)
env["REALFILE_SRC"] = sentinel
r = subprocess.run([sys.executable, GEN], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env)
if r.returncode != 0:
    print()
    print("REALFILE-SRC-FAIL (make_realfile exited %d)" % r.returncode)
    for l in (r.stderr or "").splitlines()[:5]:
        print("  " + l.strip()[:84])
    sys.exit(1)

img = os.path.join(os.environ["TEMP"], "nasdaq_rf", "img.hex")
if not os.path.exists(img):
    print()
    print("REALFILE-SRC-FAIL (no image written)")
    sys.exit(1)

first = io.open(img, encoding="ascii").readline().strip().lower()
# 'Z' is 0x5A.
ok = first == "5a"
print()
print("  sentinel file starts with b'ZZZZZZZZ'  (0x5A)")
print("  generated image starts with 0x%s        %s"
      % (first, "ok" if ok else "NOT the sentinel"))

try:
    os.unlink(sentinel)
except OSError:
    pass

print()
if not ok:
    print("REALFILE-SRC-FAIL (the image does not come from REALFILE_SRC)")
    sys.exit(1)
print("REALFILE-SRC-PASS (make_realfile builds the image from the file it is given)")
