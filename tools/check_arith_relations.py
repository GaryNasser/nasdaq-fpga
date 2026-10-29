"""Verify every arithmetic relation the report asserts - the class of error round 185 found.

Round 185 found `224` and `226` called "完全一致". Each figure traced to an artifact; the COMBINATION was wrong.
No checker combines figures, so this one does - mechanically, for the relations that can be stated as code.

### The relations worth checking

Not "every sentence with numbers" - that is not tractable. But a specific, common and checkable form:

    "A → B (+C%)"           the percentage must equal (B-A)/A
    "X = A x B"             the product must hold
    "N 个 ... 合计 S"        the sum must match
    "A: 1,226,916 / 43,428 = 28.252"   the division must hold

Each is a pattern plus a computation. The output is a list of relations that do NOT hold, which is exactly the
list a reader would otherwise have to produce by hand.

### Why the checks live here and not in the report

Because a relation that a script can verify should be verified every time the report changes, not once when
someone happens to look.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

text = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

bad = []
checked = 0


def num(s):
    return float(s.replace(",", ""))


# --- pattern 1:  A -> B (+C%)  --------------------------------------------------------
for m in re.finditer(r"(\d[\d,]*)\s*(?:→|->)\s*(\d[\d,]*)\s*[（(]\s*\+?\s*([\d.]+)\s*%\s*[)）]", text):
    checked += 1
    a, b, pct = num(m.group(1)), num(m.group(2)), float(m.group(3))
    if a == 0:
        continue
    actual = (b - a) / a * 100.0
    if abs(actual - pct) > 1.0:          # allow one point for rounding
        ln = text[:m.start()].count("\n") + 1
        bad.append("L%d  %s -> %s is %.1f%%, stated %.1f%%"
                   % (ln, m.group(1), m.group(2), actual, pct))

# --- pattern 2:  A x B = C  -----------------------------------------------------------
for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*[×x]\s*([\d,]+(?:\.\d+)?)\s*=\s*\**([\d,]+(?:\.\d+)?)\**", text):
    checked += 1
    a, b, c = num(m.group(1)), num(m.group(2)), num(m.group(3))
    if a * b == 0:
        continue
    if abs(a * b - c) / max(abs(c), 1) > 0.02:
        ln = text[:m.start()].count("\n") + 1
        bad.append("L%d  %s x %s = %.3f, stated %s"
                   % (ln, m.group(1), m.group(2), a * b, m.group(3)))

# --- pattern 3:  A / B = C  -----------------------------------------------------------
for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*/\s*([\d,]+(?:\.\d+)?)\s*=\s*\**([\d,]+(?:\.\d+)?)\**", text):
    checked += 1
    a, b, c = num(m.group(1)), num(m.group(2)), num(m.group(3))
    if b == 0:
        continue
    if abs(a / b - c) / max(abs(c), 1) > 0.02:
        ln = text[:m.start()].count("\n") + 1
        bad.append("L%d  %s / %s = %.4f, stated %s"
                   % (ln, m.group(1), m.group(2), a / b, m.group(3)))

# --- pattern 4:  a plain sum  A + B + C = D  ------------------------------------------
for m in re.finditer(r"((?:\d[\d,]*(?:\.\d+)?\s*\+\s*){2,}\d[\d,]*(?:\.\d+)?)\s*=\s*\**([\d,]+(?:\.\d+)?)\**",
                     text):
    checked += 1
    parts = [num(x) for x in re.split(r"\+", m.group(1))]
    total = num(m.group(2))
    if abs(sum(parts) - total) > 0.01 * max(abs(total), 1):
        ln = text[:m.start()].count("\n") + 1
        bad.append("L%d  %s = %.1f, stated %s"
                   % (ln, m.group(1).strip(), sum(parts), m.group(2)))

print("arithmetic relations checked: %d" % checked)
print()
if bad:
    print("ARITH-RELATION-FAIL (%d)" % len(bad))
    for b in bad:
        print("  " + b)
    sys.exit(1)

print("ARITH-RELATION-PASS (every stated relation holds within rounding)")
