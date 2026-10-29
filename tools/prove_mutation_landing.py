"""Prove check_mutation_landing rejects a new proof that replaces text without confirming it landed."""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

TOOLS = r"D:\agent\nasdaq-fpga\tools"
PLANT = os.path.join(TOOLS, "mutate_landing_probe.py")
CHECK = os.path.join(TOOLS, "check_mutation_landing.py")
RUNNER = os.path.join(TOOLS, "run_checks.py")

PROBE = """import io
REPORT = r'D:\\agent\\nasdaq-fpga\\docs\\final-report.md'
body = io.open(REPORT, encoding='utf-8', errors='surrogateescape').read()
mutated = body.replace('an anchor that is not there', 'something')
io.open(REPORT, 'w', encoding='utf-8', errors='surrogateescape').write(mutated)
print('PROBE-FAIL')
"""


def run():
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=TOOLS)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


rc0, out0 = run()
print("control : exit=%d  %s" % (rc0, "MUTATION-LANDING-PASS" if "MUTATION-LANDING-PASS" in out0 else "?"))
if rc0 != 0:
    print("MUTATION-LANDING-PROOF-FAIL (control does not pass)")
    sys.exit(1)

orig = io.open(RUNNER, encoding="utf-8").read()
bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(RUNNER, bk)
st = os.stat(RUNNER)
io.open(PLANT, "w", encoding="utf-8", newline="\n").write(PROBE)
try:
    last_check = re.findall(r"^\s*\(" + chr(34) + r"\w+" + chr(34) + r",[^\n]*\n", orig, re.M)[-1].rstrip("\n")
    injected = orig.replace(
        last_check,
        last_check + chr(10) + "    (" + chr(34) + "landing_probe_proof" + chr(34) + ", "
        + chr(34) + "a proof with no landing check" + chr(34) + ", False),",
        1)
    last_map = re.findall(r"^\s*" + chr(34) + r"\w+" + chr(34) + r": "
                          + chr(34) + r"[\w.]+\.py" + chr(34) + r",[^\n]*\n", injected, re.M)[-1].rstrip("\n")
    injected = injected.replace(
        last_map,
        last_map + chr(10) + "    " + chr(34) + "landing_probe_proof" + chr(34) + ": "
        + chr(34) + "mutate_landing_probe.py" + chr(34) + ",",
        1)
    landed = injected != orig
    io.open(RUNNER, "w", encoding="utf-8", newline="\n").write(injected)
    rc1, out1 = run()
    caught = rc1 != 0 and "MUTATION-LANDING-FAIL" in out1
    print("plant an unchecked proof   landed=%s exit=%d %s"
          % (landed, rc1, "CAUGHT" if caught else "MISSED"))
    if caught:
        for l in out1.split("\n"):
            if "prove_landing_probe" in l:
                print("   " + l.strip()[:76])
                break
finally:
    shutil.copyfile(bk, RUNNER)
    os.utime(RUNNER, (st.st_atime, st.st_mtime))
    os.unlink(bk)
    if os.path.exists(PLANT):
        os.unlink(PLANT)

rc2, out2 = run()
print("restored: exit=%d" % rc2)
print()
if landed and caught and rc2 == 0:
    print("MUTATION-LANDING-PROOF-PASS (an unchecked proof is rejected)")
    sys.exit(0)
print("MUTATION-LANDING-PROOF-FAIL")
sys.exit(1)
