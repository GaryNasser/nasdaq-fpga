"""Suite wrapper for test_report_required.py.

The check itself lives in test_report_required.py, which renames the report, runs three
document-checkers, and requires them to fail. This wrapper gives the runner the token and
exit semantics it expects.
"""
import io
import os
import subprocess
import sys

TOOLS = r"D:\agent\nasdaq-fpga\tools"
TEST = os.path.join(TOOLS, "test_report_required.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.path.exists(TEST):
    print("REPORT-REQUIRED-FAIL (no test)")
    sys.exit(1)

r = subprocess.run([sys.executable, TEST], capture_output=True, text=True,
                   encoding="utf-8", errors="replace",
                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
out = (r.stdout or "") + (r.stderr or "")
sys.stdout.write(out)
if "REPORT-REQUIRED-PASS" in out and r.returncode == 0:
    sys.exit(0)
print("REPORT-REQUIRED-FAIL (exit %d)" % r.returncode)
sys.exit(1)
