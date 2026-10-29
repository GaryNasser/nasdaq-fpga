"""Suite wrapper for test_input_probe.py."""
import io
import os
import subprocess
import sys

TOOLS = r"D:\agent\nasdaq-fpga\tools"
TEST = os.path.join(TOOLS, "test_input_probe.py")
RECOVER = os.path.join(TOOLS, "board_recover.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

for p in (TEST, RECOVER):
    if not os.path.exists(p):
        print("INPUT-PROBE-FAIL (missing %s)" % os.path.basename(p))
        sys.exit(1)

r = subprocess.run([sys.executable, TEST], capture_output=True, text=True,
                   encoding="utf-8", errors="replace",
                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
out = (r.stdout or "") + (r.stderr or "")
sys.stdout.write(out)

if "INPUT-PROBE-PASS" in out and r.returncode == 0:
    sys.exit(0)
print("INPUT-PROBE-FAIL (exit %d)" % r.returncode)
sys.exit(1)
