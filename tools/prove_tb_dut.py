"""Prove check_tb_dut fails on a bench that instantiates nothing."""
import io
import os
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
CHK = os.path.join(REPO, "tools", "check_tb_dut.py")
FAKE = os.path.join(REPO, "tools", "tb_zz_empty.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BODY = """`timescale 1ns / 1ps
module tb_zz_empty;
    initial begin
        $display("TB-ALL-PASS");
        $finish;
    end
endmodule
"""


def run():
    r = subprocess.run([sys.executable, CHK], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(CHK), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, _ = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("TB-DUT-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

io.open(FAKE, "w", encoding="utf-8", newline="\n").write(BODY)
try:
    rc1, out1 = run()
    caught = rc1 != 0
    named = "tb_zz_empty" in out1
    print("injected tb_zz_empty.v (prints PASS, instantiates nothing)")
    print("mutated : exit=%d %s%s" % (rc1, "CAUGHT" if caught else "MISSED",
                                      "" if named else "  (but does not name it)"))
    if not caught:
        for l in [x for x in out1.split("\n") if x.strip()][-3:]:
            print("   " + l.strip()[:80])
finally:
    os.unlink(FAKE)

rc2, _ = run()
print("restored: exit=%d" % rc2)
print()
if caught and named and rc2 == 0:
    print("TB-DUT-PROOF-PASS (a bench with no DUT is caught and named)")
    sys.exit(0)
print("TB-DUT-PROOF-FAIL (caught=%s named=%s restored=%s)" % (caught, named, rc2 == 0))
sys.exit(1)
