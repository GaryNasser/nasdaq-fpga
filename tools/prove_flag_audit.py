"""The paren balancer started after the opening paren, so it never counted it.

    L608  parser.add_argument('--legacy-reset', action='store_true',
    L609-611   help=...

My scan began at m.end() - the position just past the closing quote of '--legacy-reset' - so
depth started at 0 with the opening paren already behind it. The first ")" (line 608's own
argument list close) ended the scan, and the deletion removed only part of the declaration.
The flag was still declared, so the check passed.

Correct approach: back up to the '(' that opened the call, then balance from there.

This is the tenth mutation in this series that failed to land where intended. The pattern has
been consistent - the mutation, not the check, was wrong - and the fix each time was to read
the structure rather than assume it.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
DRV = os.path.join(REPO, "board", "load_overlay.py")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run():
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "check_flag_audit.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


drv = io.open(DRV, encoding="utf-8", errors="replace").read()
m = re.search(r"\n[^\n]*add_argument\(\s*['\"]--legacy-reset['\"]", drv)
if not m:
    print("FLAG-AUDIT-PROOF-FAIL (declaration not found)")
    sys.exit(1)

# Walk back to the '(' that opens this call.
open_paren = drv.rfind("(", m.start(), m.end())
if open_paren == -1:
    print("FLAG-AUDIT-PROOF-FAIL (no opening paren)")
    sys.exit(1)

# Balance from the opening paren.
depth = 0
i = open_paren
while i < len(drv):
    c = drv[i]
    if c == "(":
        depth += 1
    elif c == ")":
        depth -= 1
        if depth == 0:
            i += 1
            break
    i += 1

removed = drv[open_paren:i]
print("removing %d characters:" % len(removed))
for l in removed.split("\n")[:5]:
    print("   %s" % l.strip()[:84])
print()

mutated = drv[:open_paren] + drv[i:]
# Verify the flag is really gone from the declarations.
decl = re.search(r"add_argument\(\s*['\"]--legacy-reset", mutated)
print("flag still declared: %s" % bool(decl))

bk = tempfile.mktemp(suffix=".py")
shutil.copyfile(DRV, bk)
try:
    io.open(DRV, "w", encoding="utf-8", errors="replace", newline="\n").write(mutated)
    rc, out = run()
    caught = rc != 0
    for l in out.splitlines():
        if "FAIL" in l or "not declared" in l:
            print("   %s" % l.strip()[:86])
    print("   exit=%d %s" % (rc, "CAUGHT" if caught else "MISSED"))
finally:
    shutil.copyfile(bk, DRV)
    os.unlink(bk)

rc2, _ = run()
print()
print("restored exit=%d" % rc2)

if caught and rc2 == 0:
    sys.exit(0)
print("FLAG-AUDIT-PROOF-FAIL")
sys.exit(1)
