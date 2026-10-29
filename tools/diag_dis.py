"""Diagnose why tb_disable's baseline packet fails when tb_empty's identical packet passes.

The packet bytes are the same. The drive loop is the same shape. So the difference is in the SETUP - and the only
difference there is `set_ctrl`, which is a task in tb_disable and inline code in tb_empty.

    tb_empty     writes CTRL inline, then checks dut.enable === 1
    tb_disable   calls set_ctrl(32'h1), then checks dut.enable === 1

If `dut.enable` is 1 in both, the write is equivalent and the fault is elsewhere. If it is 0 in tb_disable, the
task's handshake differs.

### The check, rather than another guess

Print dut.enable, dut.soft_reset_pulse and the CTRL register right after set_ctrl, and again right before the
packet is driven. That distinguishes "the write did not land" from "the write landed and something reset it".
"""
import io
import os
import sys

P = r"D:\agent\nasdaq-fpga\tools\tb_disable.v"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(P, encoding="utf-8").read()

if "DBG enable=" in src:
    print("already instrumented")
    sys.exit(0)

OLD = '''    set_ctrl(32'h1);
    if (dut.enable !== 1'b1) begin
      $display("DISABLE-FAIL: enable never asserted");
      errors = errors + 1;
    end'''

NEW = '''    set_ctrl(32'h1);
    $display("DBG enable=%b soft_rst=%b", dut.enable, dut.soft_reset_pulse);
    if (dut.enable !== 1'b1) begin
      $display("DISABLE-FAIL: enable never asserted");
      errors = errors + 1;
    end'''

if OLD not in src:
    print("anchor not found")
    sys.exit(1)

src = src.replace(OLD, NEW, 1)

# Also print the state just before driving the packet.
src = src.replace('''    // One good packet with the pipeline on.
    build(0);''', '''    // One good packet with the pipeline on.
    $display("DBG before packet: enable=%b state=%0d", dut.enable, dut.state);
    build(0);
    $display("DBG packet built: n=%0d bytes %02h %02h %02h %02h", n, pkt[0], pkt[1], pkt[8], pkt[10]);''', 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(src)
print("instrumented")

import subprocess
env = {**os.environ, "PATH": r"D:\Xilinx\Vivado\2024.1\bin;" + os.environ.get("PATH", "")}
WORK = os.path.join(os.environ["TEMP"], "nasdaq_dis")
subprocess.run('xvlog.bat "%s" "%s"' % (os.path.join(os.path.dirname(os.path.dirname(P)),
                                                     "rtl", "itch", "mold64_reasm.v"), P),
               capture_output=True, text=True, env=env, cwd=WORK, shell=True)
subprocess.run('xelab.bat tb_disable -s dis2 -debug typical',
               capture_output=True, text=True, env=env, cwd=WORK, shell=True)
r = subprocess.run('xsim.bat dis2 -R --testplusarg ""',
                   capture_output=True, text=True, env=env, cwd=WORK, shell=True, timeout=120)
for l in ((r.stdout or "") + (r.stderr or "")).split("\n"):
    if "DBG" in l or "DISABLE" in l:
        print("  " + l.strip()[:82])
