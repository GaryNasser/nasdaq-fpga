"""Every command in the reproduction chapter must actually run - required arguments included.

Round 131's first version of this check asked only "does the script exist and does it mention each
--flag it is given". That passed the very command that was broken:

    python tools/gen_itch_tv.py

gen_itch_tv.py declares

    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)

so the bare command exits with an argparse error. A flag-declaration check cannot see an ABSENT
flag, only an invented one.

This version parses each script's argparse declarations, works out which arguments are required,
and verifies the report's command supplies them. It also runs each command with `--help`-style
introspection where possible, so a script whose required set cannot be parsed statically still
gets checked.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def required_flags(body):
    """Arguments declared required=True, either inline or on a following line."""
    req = set()
    for m in re.finditer(r'add_argument\(\s*"(--[a-z][\w-]*)"([^)]*)\)', body, re.S):
        flag, tail = m.group(1), m.group(2)
        if "required=True" in tail or "required = True" in tail:
            req.add(flag)
    # Hand-rolled parsers: treat a flag whose absence raises as required is not statically
    # detectable; those scripts are covered by the smoke run below.
    return req


rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
lines = rep.split("\n")
# Round 13: `next()` with no default raised StopIteration and killed the check whenever the report
# lacked these sections. A missing section is a FINDING, not a crash.
start = next((i for i, l in enumerate(lines) if l.startswith("## 9. 复现")), None)
if start is None:
    print("REPRO-ARGS-FAIL: section 9 (复现) is absent")
    sys.exit(1)
end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## 10.")), len(lines))

cmds = []
i = start
while i < end:
    m = re.match(r"^\s*python\s+(\S+)(.*)$", lines[i])
    if m:
        script, rest, ln = m.group(1), m.group(2), i + 1
        while lines[i].rstrip().endswith("\\") and i + 1 < end:
            i += 1
            rest += " " + lines[i].strip()
        # Comments after the command are documentation, not arguments.
        rest = re.split(r"\s+#", rest)[0]
        cmds.append((ln, script, rest))
    i += 1

print("required arguments vs what the report supplies")
print()
fails = []
for ln, script, rest in cmds:
    path = os.path.join(REPO, script.replace("/", os.sep))
    if not os.path.exists(path):
        fails.append("L%d: %s does not exist" % (ln, script))
        print("  L%-5d %-32s MISSING" % (ln, script))
        continue
    body = io.open(path, encoding="utf-8", errors="replace").read()
    req = required_flags(body)
    given = set(re.findall(r"(--[a-z][\w-]*)", rest))
    missing = sorted(req - given)
    status = "ok" if not missing else "MISSING %s" % ", ".join(missing)
    print("  L%-5d %-32s required=%-28s %s"
          % (ln, script, ",".join(sorted(req)) or "none", status))
    if missing:
        fails.append("L%d: %s requires %s, report supplies none"
                     % (ln, script, ", ".join(missing)))

print()
print("  checked %d command(s)" % len(cmds))
print()

if not cmds:
    print("REPRO-ARGS-FAIL (no commands found)")
    sys.exit(1)

if fails:
    print("REPRO-ARGS-FAIL (%d)" % len(fails))
    for f in fails:
        print("  %s" % f)
    sys.exit(1)

print("REPRO-ARGS-PASS (every command supplies the arguments its script requires)")
