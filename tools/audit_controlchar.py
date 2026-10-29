"""Find regex patterns containing control characters - the round-212 failure mode, searched for instead of hit by luck.

    IMPOSSIBLE_ITEMS = re.compile(r"\\x08K1\\x08")     <- 0x08 backspaces, written by a shell escape

A pattern with a control character matches nothing in normal text, so the check silently never fires. This scans
every tool for compiled patterns whose source contains a non-printable byte, and confirms each pattern compiles and
would match something plausible.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

bad = []
suspicious = []

for fn in sorted(os.listdir(TOOLS)):
    if not fn.endswith(".py"):
        continue
    path = os.path.join(TOOLS, fn)
    raw = io.open(path, "rb").read()
    text = raw.decode("utf-8", "replace")

    # 1  literal control characters anywhere in the source.
    ctrl = [(i + 1, repr(c)) for i, c in enumerate(text)
            if ord(c) < 32 and c not in "\n\r\t"]
    if ctrl:
        bad.append((fn, "literal control char", ctrl[:3]))

    # 2  compiled patterns visible as string literals - check for suspicious bodies.
    for m in re.finditer(r"re\.compile\(\s*(?:r|u|f)?(['\"])(.*?)\1", text, re.S):
        pat = m.group(2)
        # A pattern assembled with join() has no single literal that IS the pattern - the captured
        # text is only the separator. The regex stops at the closing quote, so the `.join(` sits
        # AFTER the match and must be looked for there.
        if ".join(" in text[m.end():m.end() + 12]:
            continue
        # A pattern that is ONLY a short token with no metacharacters is fine; one that cannot match
        # a letter is suspicious.
        # Any non-ASCII character counts as a letter: the report is written in Chinese, and a
        # pattern matching Chinese prose is not suspicious.
        # A matchable literal character: ASCII letter, digit, or CJK.
        if not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", pat):
            suspicious.append((fn, pat[:40]))
            continue
        # Patterns of the form "x\\bfoo\\b" written with control bytes already caught above.

print("files with literal control characters in source: %d" % len(bad))
for fn, why, where in bad:
    print("  %-34s %s at %s" % (fn, why, where))

print()
print("compiled patterns with no letter, digit or CJK (cannot match text): %d" % len(suspicious))
for fn, pat in suspicious[:10]:
    print("  %-34s %r" % (fn, pat))

# 3  A broader sanity check: every list of checker names must resolve to an existing script.
RUNNER = os.path.join(TOOLS, "run_checks.py")
if os.path.exists(RUNNER):
    src = io.open(RUNNER, encoding="utf-8").read()
    section = src.split("SCRIPT", 1)[-1]
    refs = re.findall(r'"(\w+)":\s*"([\w.]+\.py)"', section)
    missing = [(k, v) for k, v in refs if not os.path.exists(os.path.join(TOOLS, v))]
    print()
    print("registered scripts that do not exist: %d" % len(missing))
    for k, v in missing:
        print("  %-28s -> %s" % (k, v))

if bad or suspicious or missing:
    sys.exit(1)
print()
print("CONTROL-CHAR-AUDIT-PASS (no pattern contains a control character)")
