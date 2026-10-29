"""Prove check_packet_design fails on the three regressions it guards.

    1  the report reverts to calling the buffer single-packet  (the pre-round-109 text)
    2  the RTL reverts s_can_write to gate on pkt_hold
    3  the report stops naming fifo_has_room

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
REPORT = os.path.join(REPO, "docs", "final-report.md")
CHK = os.path.join(REPO, "tools", "check_packet_design.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rtl = io.open(RTL, encoding="latin-1").read()
rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

CASES = []

# 1. Report back to "current buffer is single-packet".
CASES.append(("report says single-packet today", REPORT,
              rep.replace("**缓冲结构（已更新）**", "**缓冲结构**：当前 `mold64_reasm` 的包缓冲是**单包 4 KB** 结构。\n\n> **缓冲结构（已更新）**", 1),
              "utf-8", "surrogateescape"))

# 2. RTL flow control reverted.
m = re.search(r"wire s_can_write = enable && fifo_has_room;", rtl)
if m:
    CASES.append(("RTL gates on pkt_hold", RTL,
                  rtl[:m.start()] + "wire s_can_write = enable && !pkt_hold;"
                  + rtl[m.end():], "latin-1", "replace"))

# 3. Report stops naming fifo_has_room.
CASES.append(("report drops fifo_has_room", REPORT,
              rep.replace("fifo_has_room", "缓冲余量"), "utf-8", "surrogateescape"))

results = []
for label, path, mutated, enc, err in CASES:
    orig = io.open(path, encoding=enc, errors=err).read()
    if mutated == orig:
        print("%-34s NOT APPLIED" % label)
        continue
    bk = tempfile.mktemp(suffix=os.path.splitext(path)[1])
    shutil.copyfile(path, bk)
    try:
        io.open(path, "w", encoding=enc, errors=err, newline="\n").write(mutated)
        rc, out = run()
        caught = rc != 0
        results.append((label, caught))
        detail = next((l.strip() for l in out.splitlines()
                       if "PACKET-DESIGN-FAIL" in l or "YES" in l or "gate" in l), "")
        print("%-34s exit=%d %s  %s" % (label, rc, "CAUGHT" if caught else "MISSED",
                                        detail[:36]))
    finally:
        shutil.copyfile(bk, path)
        os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)
print()
if results and all(c for _, c in results) and rc2 == 0:
    sys.exit(0)
print("PACKET-DESIGN-PROOF-FAIL")
sys.exit(1)
