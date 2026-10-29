"""Prove check_parse_regmap fails on a wrong driver offset for a parser register."""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_parse_regmap.py")
DRV = os.path.join(REPO, "board", "load_overlay.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("PARSE-REGMAP-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

body = io.open(DRV, encoding="utf-8", errors="surrogateescape").read()
m = re.search(r"(REG_IP_DROP_LEN_CNT\s*=\s*)0x([0-9A-Fa-f]+)", body)
if not m:
    print("PARSE-REGMAP-PROOF-INCONCLUSIVE (REG_IP_DROP_LEN_CNT not found)")
    sys.exit(0)

old = int(m.group(2), 16)
new = old + 4
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, bk)
try:
    io.open(DRV, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(
        body[:m.start(2)] + ("%X" % new) + body[m.end(2):])
    print("REG_IP_DROP_LEN_CNT: 0x%02X -> 0x%02X" % (old, new))
    rc1, out1 = run()
    caught = rc1 != 0
    named = "DROP_LEN_CNT" in out1
    print("mutated : exit=%d %s%s" % (rc1, "CAUGHT" if caught else "MISSED",
                                      "" if named else "  (but does not name it)"))
finally:
    shutil.copyfile(bk, DRV)
    os.unlink(bk)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if caught and named and rc2 == 0:
    print("PARSE-REGMAP-PROOF-PASS (a wrong parser register offset is caught and named)")
    sys.exit(0)
print("PARSE-REGMAP-PROOF-FAIL (caught=%s named=%s restored=%s)" % (caught, named, rc2 == 0))
sys.exit(1)
