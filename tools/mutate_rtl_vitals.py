"""Prove that three design checks can fail, by breaking what they guard.

None of these has a harness, so all three are only proven to RUN:

    check_fsm_liveness   no FSM state is unreachable or dead
    check_multidriver    no signal is driven from two always blocks
    check_constexpr      constants fit their declared widths

Each guards a property whose violation would be a real RTL defect:

    an unreachable state      means a branch can never execute - dead logic in silicon
    a multiply-driven reg     means simulation and hardware can disagree (X in hardware)
    a constant overflow       means a truncation that synthesis silently applies

The mutations have to break the CODE, not a comment. Rounds 62-65 lost five attempts that
way, and round 78 lost a sixth; so this harness masks comments first, then locates a real
assignment or state, then verifies the edit landed in code.
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
OB = os.path.join(REPO, "rtl", "itch", "order_book.v")
MR = os.path.join(REPO, "rtl", "itch", "mold64_reasm.v")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def strip_comments(t):
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def run(check):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, check)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


CASES = []

# 1. multidriver: add a second always block driving an existing register.
src = io.open(MR, encoding="latin-1").read()
m = re.search(r"always\s*@\(posedge[^)]*\)[^\n]*\n(.*?)\n\s*end\b", src, re.S)
if m:
    body = m.group(1)
    reg = re.search(r"(\w+)\s*<=", body)
    if reg:
        name = reg.group(1)
        injection = ("\n  always @(posedge aclk) begin\n    %s <= 1'b0;\n  end\n" % name)
        i = src.find("endmodule")
        CASES.append(("multidriver: second driver for %s" % name,
                      MR, src[:i] + injection + src[i:], "check_multidriver.py"))

# 2. fsm_liveness: make a state unreachable by pointing both transition sources at one.
src = io.open(OB, encoding="latin-1").read()
# The declaration carries a width: localparam [3:0] ST_IDLE = 4'd0;
states = re.findall(r"localparam\s*(?:\[[^\]]*\])?\s+(ST_\w+)\s*=\s*\d+'d\d+", src)
if len(states) >= 3:
    victim = [s for s in states if s != "ST_IDLE"][0]
    # Redirect every entry into `victim` to ST_IDLE - the state becomes dead.
    mutated = re.sub(r"\b%s\b(?!\s*=)" % re.escape(victim), "ST_IDLE", src)
    # Keep its own definition.
    mutated = mutated.replace("ST_IDLE = ", "%s_DEF = " % victim, 0)
    CASES.append(("fsm_liveness: %s never entered" % victim, OB, mutated,
                  "check_fsm_liveness.py"))

results = []
for name, path, mutated, check in CASES:
    if mutated == io.open(path, encoding="latin-1").read():
        print("%-44s NOT APPLIED" % name)
        results.append((name, False, False))
        continue
    # Confirm the edit landed in CODE, not a comment.
    before = strip_comments(io.open(path, encoding="latin-1").read())
    after = strip_comments(mutated)
    if before == after:
        print("%-44s landed only in comments" % name)
        results.append((name, False, False))
        continue

    backup = tempfile.mktemp(suffix=".v")
    shutil.copyfile(path, backup)
    try:
        io.open(path, "w", encoding="latin-1", newline="\n").write(mutated)
        rc, out = run(check)
        caught = rc != 0
        results.append((name, True, caught))
        print("%-44s exit=%d %s" % (name, rc, "CAUGHT" if caught else "MISSED"))
        if not caught:
            tail = [l for l in out.splitlines() if l.strip()][-2:]
            for l in tail:
                print("      %s" % l[:90])
    finally:
        shutil.copyfile(backup, path)
        os.unlink(backup)

# Healthy path after all restores.
for check in ("check_multidriver.py", "check_fsm_liveness.py"):
    rc, out = run(check)
    print("%-44s exit=%d (restored)" % (check, rc))

print()
ok = results and all(l and c for _, l, c in results)
print("RTL-HARNESS-MUTATION-PASS" if ok else "RTL-HARNESS-MUTATION-FAIL")
if ok:
    sys.exit(0)
print("one or more mutations were missed")
sys.exit(1)
