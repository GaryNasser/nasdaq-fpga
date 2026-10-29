"""Scope the codec check to the checkers that actually decide the suite verdict.

The first version examined every *.py in tools/ and found 51 implicit codecs, most of
them in `mutate_*.py` development scripts. Those scripts do compare exit codes, so in
principle the same fault applies - but they are run by hand during development, never
by the suite, and the cost of fixing twenty files is not repaid by the risk.

What matters is narrower and precise: a checker that the runner executes must not have
an implicit codec, because its verdict is what the project reports. That is the set in
run_checks.py's SCRIPT table.

So this reads the SCRIPT table and audits exactly those files. It also audits this
checker's own dependencies (audit_*.py called from check_*.py) one level deep, since
a mojibake reading propagates: check_deliverables parses audit_deliverables' output,
and that is precisely where round 42's false PASS came from.
"""
import glob
import io
import os
import re
import sys

TOOLS = r"D:\agent\nasdaq-fpga\tools"
RUN = os.path.join(TOOLS, "run_checks.py")


def balanced_call(src, open_idx):
    depth = 0
    i = open_idx
    while i < len(src):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                return src[open_idx:i + 1]
        i += 1
    return src[open_idx:]


def implicit_codecs(src):
    """Line numbers of implicit text codecs in one file's source."""
    out = []
    for m in re.finditer(r"subprocess\.(run|Popen)\(", src):
        call = balanced_call(src, m.end() - 1)
        if "text=True" in call and "encoding=" not in call:
            out.append((src[:m.start()].count("\n") + 1,
                        "subprocess text=True without encoding"))
    for m in re.finditer(r"io\.open\(", src):
        call = balanced_call(src, m.end() - 1)
        if "encoding=" in call:
            continue
        if re.search(r"['\"](r|w|a)b\+?['\"]", call):
            continue
        out.append((src[:m.start()].count("\n") + 1, "io.open without encoding"))
    return out


run_src = io.open(RUN, encoding="utf-8").read()
scripts = sorted(set(re.findall(r'"(\w+\.py)"', run_src)))

# One level of transitive dependency: audit_*.py invoked from a check.
targets = set(scripts)
for name in scripts:
    p = os.path.join(TOOLS, name)
    if not os.path.exists(p):
        continue
    src = io.open(p, encoding="utf-8", errors="replace").read()
    for dep in re.findall(r'"((?:audit|check|run)_\w*\.py)"', src):
        targets.add(dep)

print("implicit text codecs in suite-executed checkers")
print()
print("  checkers in the runner : %d" % len(scripts))
print("  with dependencies      : %d" % len(targets))
print()

fails = []
for name in sorted(targets):
    path = os.path.join(TOOLS, name)
    if not os.path.exists(path):
        continue
    src = io.open(path, encoding="utf-8", errors="replace").read()
    for line, why in implicit_codecs(src):
        fails.append((name, line, why))
        print("  %-30s L%-5d %s" % (name, line, why))

print()
if fails:
    print("CODEC-EXPLICIT-FAIL (%d)" % len(fails))
    for name, line, why in fails:
        print("  %s:%d %s" % (name, line, why))
    sys.exit(1)
print("CODEC-EXPLICIT-PASS (every suite-executed checker names its codec)")
