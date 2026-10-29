"""Only 10 of 13 rows parsed: the tuple regex breaks on commas inside the lambda.

The rows are:

    ("DMA→DDR 端到端吞吐",
     lambda: False,
     "未测（§11.4 明确：上表是流水线吞吐，不是 DMA→DDR 端到端）"),

`lambda[^,]*?` stops at the first comma, and several lambdas contain commas inside function
calls - `os.path.exists(os.path.join(REPO, "x"))` has three. So those rows never matched,
and the check then complained that DMA was "not marked as a gap" when in fact it was simply
not seen.

Rather than write a fourth regex over source text, parse the tuples properly: find the
`("` starts, then scan forward balancing parentheses and quotes to the closing `),`. That
is a small state machine and it is exact.

This is the same lesson as the register-map decode in round 66: when the structure is nested,
count parentheses instead of trying to describe the nesting with a pattern.
"""
import io
import os
import re
import sys

P = r"D:\agent\nasdaq-fpga\tools\check_deliv_lambdas.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(P, encoding="utf-8").read()

OLD = '''body = BLOCK.group(1)
TUPLES = re.findall(
    r'\\(\\s*"([^"]+)"\\s*,\\s*(lambda[^,]*?)\\s*,\\s*"([^"]*)"\\s*\\)', body, re.S)'''

NEW = '''body = BLOCK.group(1)


def split_tuples(text):
    """Split the ITEMS body into top-level tuples, balancing parens and quotes."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "(":
            i += 1
            continue
        start = i
        depth = 0
        in_str = False
        while i < n:
            c = text[i]
            if in_str:
                if c == "\\\\":
                    i += 2
                    continue
                if c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        out.append(text[start:i])
    return out


TUPLES = []
for t in split_tuples(body):
    nm = re.match(r'\\(\\s*"([^"]+)"\\s*,', t)
    wh = re.search(r',\\s*"([^"]*)"\\s*\\)\\s*$', t)
    lm = re.search(r"lambda[^\\n]*", t)
    if nm and wh:
        TUPLES.append((nm.group(1), lm.group(0) if lm else "?", wh.group(1)))'''

if OLD in src:
    src = src.replace(OLD, NEW, 1)
    applied = True
else:
    applied = False

if not applied:
    print("regex block not found")
    i = src.find("TUPLES = re.findall")
    print(repr(src[i - 30:i + 200]))
    sys.exit(1)

io.open(P, "w", encoding="utf-8", newline="\n").write(src)
compile(io.open(P, encoding="utf-8").read(), P, "exec")
print("paren-balancing parser installed; syntax ok")
