"""Prove audit_reimpl fails when a script references another tool's output without importing it.

`audit_reimpl` was edited three times and has never had a proof. **It is a detector, and detectors in this project
are wrong about one time in seven** - so its clean verdict carries no weight until it can be made to fail.

The test: inject a new script that names `verdict` and does not import `board_recover`, then confirm the audit
reports it.
"""
import io
import os
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
AUDIT = os.path.join(REPO, "tools", "audit_reimpl.py")
FAKE = os.path.join(REPO, "tools", "zz_fake_checker.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, AUDIT], capture_output=True, encoding="utf-8", errors="replace",
                       cwd=os.path.dirname(AUDIT), timeout=600)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))


rc0, out0 = run()
print("baseline: exit=%d" % rc0)
if rc0 != 0:
    print("REIMPL-PROOF-FAIL (baseline does not pass)")
    sys.exit(1)

# A script that names a sibling's output but imports nothing from it, and falls in no family.
FAKE_BODY = '''"""A deliberately unclassifiable script: it mentions verdict without importing board_recover."""
import io
import subprocess
import sys

r = subprocess.run(["python", "board_recover.py"], capture_output=True)
text = (r.stdout or b"").decode()
print("verdict present:", "GOLDEN-OK" in text)
sys.exit(0)
'''

io.open(FAKE, "w", encoding="utf-8", newline="\n").write(FAKE_BODY)
try:
    rc1, out1 = run()
    caught = rc1 != 0
    named = "zz_fake_checker" in out1
    print("injected zz_fake_checker.py")
    print("mutated : exit=%d %s%s" % (rc1, "CAUGHT" if caught else "MISSED",
                                      "" if named else "  (but does not name it)"))
    if not caught:
        for l in [x for x in out1.split("\n") if x.strip()][-4:]:
            print("   " + l.strip()[:80])
finally:
    os.unlink(FAKE)

rc2, _ = run()
print("restored: exit=%d" % rc2)

print()
if caught and named and rc2 == 0:
    print("REIMPL-PROOF-PASS (an unclassifiable cross-tool reference is caught and named)")
    sys.exit(0)
print("REIMPL-PROOF-FAIL (caught=%s named=%s restored=%s)" % (caught, named, rc2 == 0))
sys.exit(1)
