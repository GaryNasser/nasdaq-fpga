"""Final audit: every remaining 200 MHz mention must be historical, not a claim."""
import io
import sys

# Write UTF-8 regardless of the console codec: these checkers echo text
# from Chinese documents, and a GBK console raises on it - crashing the
# check af the very moment it is reporting a problem.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PATH = r"D:\agent\nasdaq-fpga\docs\final-report.md"
HIST = ("200.23", "曾", "废弃", "常量", "原定", "当时频点", "先改")

text = io.open(PATH, encoding="utf-8").read()
rows = []
bad = 0
for i, line in enumerate(text.split("\n"), 1):
    if "200 MHz" not in line and "100/200" not in line:
        continue
    kind = "HISTORICAL" if any(k in line for k in HIST) else "** CLAIM **"
    if kind != "HISTORICAL":
        bad += 1
    rows.append("  %-12s line %-4d %s" % (kind, i, line.strip()[:90]))

out = io.open(r"C:\Users\qingx\AppData\Local\Temp\audit200.txt", "w", encoding="utf-8")
out.write("200 MHz mentions in the report: %d\n" % len(rows))
out.write("\n".join(rows))
out.write("\n\nclaim-shaped mentions remaining: %d\n" % bad)
out.write("CLOCK-AUDIT-PASS\n" if bad == 0 else "CLOCK-AUDIT-FAIL\n")
out.close()

print("mentions: %d, claim-shaped remaining: %d" % (len(rows), bad))
print("CLOCK-AUDIT-PASS" if bad == 0 else "CLOCK-AUDIT-FAIL")
if bad != 0:
    sys.exit(1)  # the runner decides PASS from the exit code alone
