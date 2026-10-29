"""Wrap test_chunk_fit with a verdict token so the suite can run it.

test_chunk_fit.py already prints CHUNK-FIT-PASS / CHUNK-FIT-FAIL and sets its exit code.
The suite needs only a stable token and exit semantics, both of which exist - so this
wrapper exists purely to give it the check_ prefix the runner expects.

Rather than duplicate the logic, it execs the test in-process and reports.
"""
import io
import os
import subprocess
import sys

TOOLS = r"D:\agent\nasdaq-fpga\tools"
TEST = os.path.join(TOOLS, "test_chunk_fit.py")
SWEEP = os.path.join(TOOLS, "chunk_sweep.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

for p in (TEST, SWEEP):
    if not os.path.exists(p):
        print("CHUNK-FIT-FAIL (missing %s)" % os.path.basename(p))
        sys.exit(1)

r = subprocess.run([sys.executable, TEST], capture_output=True, text=True,
                   encoding="utf-8", errors="replace",
                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
out = (r.stdout or "") + (r.stderr or "")
sys.stdout.write(out)

if "CHUNK-FIT-PASS" in out and r.returncode == 0:
    sys.exit(0)
print("CHUNK-FIT-FAIL (exit %d)" % r.returncode)
sys.exit(1)
