"""Harden run_sims.py: a token printed before a failure is not a pass.

The runner decided PASS from one expression:

    got = token in r.stdout

and xsim reports `Fatal:` while still exiting 0, so neither the token nor the exit
code distinguishes "passed" from "printed PASS then crashed".

Demonstrated with tools/tb_trap.v:

    TRAP-PASS
    TRAP-POST-TOKEN-ERROR
    Fatal: failure AFTER the pass token
                                    xsim exit code: 0

A real testbench that prints its token and then trips a late monitor assertion would
have been recorded as PASS, and the suite would have printed SIMSUITE-PASS.

THE FIX

A suite passes only when ALL of these hold:
  * the token appears in stdout;
  * xsim's exit code is 0;
  * stdout contains no `Fatal:` / `ERROR:` line;
  * the simulation actually ended - either `$finish called` or a normal end banner,
    so a run truncated by a timeout cannot pass on a token printed early.

Each condition is reported separately, so a failure says which one broke.
"""
import io
import re

PATH = r"D:\agent\nasdaq-fpga\tools\run_sims.py"
src = io.open(PATH, encoding="utf-8").read()

OLD = """    r = sh("xsim.bat %s -runall" % tb[:-2], d)
    got = token in r.stdout
    print("[%s] %-10s %s" % ("PASS" if got else "FAIL", label, token))
    if not got:
        tail = [l.strip() for l in r.stdout.splitlines() if l.strip()][-4:]
        for line in tail:
            print("       | " + line)
    results.append((label, "PASS" if got else "FAIL"))"""

NEW = """    r = sh("xsim.bat %s -runall" % tb[:-2], d)

    # A suite passes only if the token appeared AND the simulation really ended
    # cleanly. Checking the token alone let a testbench print PASS and then trip a
    # $fatal be recorded as a pass - demonstrated by tools/tb_trap.v, where xsim
    # prints "Fatal:" yet still exits 0.
    saw_token = token in r.stdout
    clean_exit = (r.returncode == 0)
    fatal = re.search(r"^(Fatal|ERROR):", r.stdout, re.M) is not None
    finished = ("$finish called" in r.stdout
                or "Simulation completed" in r.stdout
                or "normal end" in r.stdout.lower())
    got = saw_token and clean_exit and not fatal and finished

    print("[%s] %-10s %s" % ("PASS" if got else "FAIL", label, token))
    if not got:
        reasons = []
        if not saw_token:
            reasons.append("token not printed")
        if not clean_exit:
            reasons.append("xsim exit %d" % r.returncode)
        if fatal:
            reasons.append("Fatal/ERROR in output")
        if not finished:
            reasons.append("simulation did not reach $finish")
        print("       | " + ", ".join(reasons))
        tail = [l.strip() for l in r.stdout.splitlines() if l.strip()][-4:]
        for line in tail:
            print("       | " + line)
    results.append((label, "PASS" if got else "FAIL"))"""

assert OLD in src, "verdict block not found"
src = src.replace(OLD, NEW, 1)

if "import re" not in src.split("def ")[0]:
    src = src.replace("import os", "import os\nimport re", 1)

io.open(PATH, "w", encoding="utf-8", newline="\n").write(src)
after = io.open(PATH, encoding="utf-8").read()
print("verdict hardened: %s" % ("saw_token" in after))
print("import re present: %s" % bool(re.search(r"^import re$", after, re.M)))
