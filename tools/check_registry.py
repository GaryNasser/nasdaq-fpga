"""Every registered check must map to exactly one script, and vice versa.

Every check in the suite must have a script, and every script entry must be a registered check.

Round 248: `SCRIPT` had 219 entries while `CHECKS` had 218. The extra one - `consistency_proof` - was a mapping
left behind when `more_proofs` took over proving consistency. **It was never run, and nothing noticed.**

The consequence is small but exactly the kind this project has been removing: **a name in the registry that does not
correspond to anything executed.** A reader counting entries would over-report the suite.

Both directions matter:

    a CHECKS entry with no SCRIPT mapping     the runner cannot find the script and would crash or skip
    a SCRIPT mapping with no CHECKS entry     dead configuration that inflates the count
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
RUNNER = os.path.join(REPO, "tools", "run_checks.py")
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(RUNNER, encoding="utf-8").read()

# The CHECKS table.
body_start = src.find("CHECKS")
if body_start < 0:
    print("REGISTRY-FAIL (no CHECKS table)")
    sys.exit(1)
table = src[body_start:].split("]\n", 1)[0]
checks = re.findall(r'^\s*\("(\w+)",\s*"([^"]*)"', table, re.M)
check_names = [n for n, _ in checks]

# The SCRIPT mapping.
mapping = dict(re.findall(r'"(\w+)":\s*"([\w.]+\.py)"', src))

print("CHECKS entries : %d" % len(check_names))
print("SCRIPT entries : %d" % len(mapping))
print()

problems = []

# 1  a check with no script
for n in check_names:
    if n not in mapping:
        problems.append(("check has no script mapping", n))
    else:
        p = os.path.join(TOOLS, mapping[n])
        if not os.path.exists(p):
            problems.append(("script file does not exist", "%s -> %s" % (n, mapping[n])))

# 2  a mapping with no check
for n in sorted(mapping):
    if n not in check_names:
        problems.append(("script mapping has no check entry (never runs)", n))

# 3  a script mapped but not registered anywhere, listed as an orphan file
unused = []
for f in sorted(os.listdir(TOOLS)):
    if f.startswith(("check_", "prove_", "mutate_", "audit_")) and f.endswith(".py"):
        if f not in mapping.values():
            unused.append(f)

print("orphan tool scripts on disk (not referenced by SCRIPT): %d" % len(unused))
for f in unused[:10]:
    print("   " + f)

print()
print("problems: %d" % len(problems))
for why, what in problems:
    print("   %-46s %s" % (why, what))

print()
if problems:
    print("REGISTRY-FAIL (%d)" % len(problems))
    sys.exit(1)
print("REGISTRY-PASS (%d checks, %d script mappings, one-to-one)" % (len(check_names), len(mapping)))
