"""Prove check_fifo_docs fails on the three regressions it guards.

    1  revert s_can_write to gate on pkt_rx_done      (the pre-rewrite flow control)
    2  remove the byte-FIFO sentence from the header
    3  remove the status update from the bring-up log

Each must fail.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
RTL = os.path.join(REPO, "rtl", "itch", "mold64_reasm.v")
LOG = os.path.join(REPO, "docs", "bringup-defects.md")
CHK = os.path.join(REPO, "tools", "check_fifo_docs.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rtl = io.open(RTL, encoding="latin-1").read()
log = io.open(LOG, encoding="utf-8", errors="surrogateescape").read()

CASES = []

m = re.search(r"wire s_can_write = enable && fifo_has_room;", rtl)
if m:
    CASES.append(("flow control reverted", RTL,
                  rtl[:m.start()] + "wire s_can_write = enable && !pkt_hold;"
                  + rtl[m.end():], "latin-1"))

# Remove the whole byte-FIFO NOTE block, not just one line - the block has several
# sentences citing fifo_has_room, and removing one leaves the check satisfied.
m = re.search(r"//          NOTE:[^\n]*\n(?:\s*//[^\n]*\n){0,6}", rtl)
if m:
    CASES.append(("header FIFO sentence removed", RTL, rtl[:m.start()] + rtl[m.end():],
                  "latin-1"))

m = re.search(r"> \*\*Status update\*\*:[^\n]*\n(?:>[^\n]*\n){0,3}", log)
if m:
    CASES.append(("log status update removed", LOG, log[:m.start()] + log[m.end():],
                  "utf-8"))

results = []
for label, path, mutated, enc in CASES:
    orig = io.open(path, encoding=enc, errors="replace").read()
    if mutated == orig:
        print("%-32s NOT APPLIED" % label)
        continue
    bk = tempfile.mktemp(suffix=os.path.splitext(path)[1])
    shutil.copyfile(path, bk)
    try:
        io.open(path, "w", encoding=enc, errors="replace",
                newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        results.append((label, caught))
        detail = next((l.strip() for l in out.splitlines()
                       if "FIFO-DOC-FAIL" in l or "not describe" in l
                       or "still says" in l or "depends on a packet" in l), "")
        print("%-32s exit=%d %s  %s" % (label, rc, "CAUGHT" if caught else "MISSED",
                                        detail[:38]))
    finally:
        shutil.copyfile(bk, path)
        os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("FIFO-DOC-PROOF-FAIL")
sys.exit(1)
