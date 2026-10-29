"""Suite wrapper for test_golden_exit.py."""
import io
import os
import subprocess
import sys

TOOLS = r"D:\agent\nasdaq-fpga\tools"
TEST = os.path.join(TOOLS, "test_golden_exit.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(TEST):
    print("GOLDEN-EXIT-FAIL (no test)")
    sys.exit(1)

r = subprocess.run([sys.executable, TEST], capture_output=True, text=True,
                   encoding="utf-8", errors="replace",
                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
out = (r.stdout or "") + (r.stderr or "")
sys.stdout.write(out)
if "GOLDEN-EXIT-PASS" in out and r.returncode == 0:
    sys.exit(0)
print("GOLDEN-EXIT-FAIL (exit %d)" % r.returncode)
sys.exit(1)
