"""Which board-facing scripts run the PYNQ driver locally instead of over ssh?

Round 73 found chunk_sweep.py doing exactly that, and it would have failed at the worst
possible moment. The question now: is it the only one?

A script is "board-facing" if it invokes load_overlay.py or opens an ssh connection. The
fault to look for is invoking the driver with a local interpreter - `sys.executable`,
`subprocess.run([sys.executable, DRIVER...])` - because that runs on the development host,
where numpy/pynq/XRT do not exist.

The correct form, from board_recover.py:

    cmd = 'cd %s && sudo -n env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python load_overlay.py ...'
    sh(['ssh', ..., BOARD, cmd])

This classifies every tools/*.py that mentions load_overlay.py.
"""
import glob
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

board_facing, local_runs, remote_runs, other, mocks = [], [], [], [], []

# Mutation harnesses and their own tests necessarily embed the broken form they inject, so
# scanning them would report the harness rather than the project. Excluded narrowly, and
# counted, so the exclusion cannot quietly grow.
HARNESS = re.compile(r"^(mutate_|test_).*\.py$")
skipped_harness = []

for path in sorted(glob.glob(os.path.join(TOOLS, "*.py"))):
    name = os.path.basename(path)
    if HARNESS.match(name):
        skipped_harness.append(name)
        continue
    src = io.open(path, encoding="utf-8", errors="replace").read()
    code = re.sub(r"#[^\n]*", "", src)

    mentions_driver = "load_overlay.py" in code or "DRIVER" in code
    uses_ssh = '"ssh"' in code or "'ssh'" in code
    if not (mentions_driver or uses_ssh):
        continue
    board_facing.append(name)

    # Local invocation of the driver.
    local = re.search(
        r"(sys\.executable[^\n]*DRIVER|subprocess\.run\(\s*\[\s*sys\.executable[^\n]*"
        r"load_overlay)", code)
    # Remote invocation: ssh present AND the pynq venv path used.
    remote = ("/usr/local/share/pynq-venv/bin/python" in code
              or "pynq-venv" in code)

    # A script may run the driver locally because it BUILDS the driver's dependencies
    # first - a mock. That differs from running the real driver on a host that cannot
    # import numpy, and only the latter is the round-73 fault.
    # Two ways a script supplies the driver's dependencies:
    #   an embedded stand-in (mock_run.py: NUMPY_SRC, a fake pynq)
    #   a populated directory on PYTHONPATH (check_guard.py: PYTHONPATH=WORK, module write)
    provides_mock = bool(re.search(
        r"NUMPY_SRC|numpy stand-in|fake pynq|MockPynq|pyfake|sys\.modules\["
        r"|PYTHONPATH\"\]\s*="          # points the driver at a sandbox
        r"|env\[\"PYTHONPATH\"\]",     # same, spelled differently
        code))

    if local and not remote:
        if provides_mock:
            mocks.append(name)
        else:
            local_runs.append((name, local.group(0)[:70].replace("\n", " ")))
    elif remote:
        remote_runs.append(name)
    else:
        other.append(name)

print("scripts that talk to the board: %d" % len(board_facing))
print("  (skipped %d mutation/test harness file(s): %s)"
      % (len(skipped_harness), ", ".join(skipped_harness) or "none"))
print()
print("  run the driver REMOTELY (correct): %d" % len(remote_runs))
for n in remote_runs:
    print("     %s" % n)
print()
print("  run the driver LOCALLY (wrong machine): %d" % len(local_runs))
for n, frag in local_runs:
    print("     %-28s %s" % (n, frag))
print()
print("  run locally against a MOCK (correct): %d" % len(mocks))
for n in mocks:
    print("     %s" % n)
print()
print("  neither pattern matched: %d" % len(other))
for n in other:
    print("     %s" % n)

print()
if local_runs:
    print("BOARD-RUN-FAIL (%d)" % len(local_runs))
    for n, _ in local_runs:
        print("  %s invokes the PYNQ driver on the development host" % n)
    sys.exit(1)
if not board_facing:
    print("BOARD-RUN-FAIL (no board-facing scripts found - the scan would be vacuous)")
    sys.exit(1)
print("BOARD-RUN-PASS (no script runs the PYNQ driver locally)")
