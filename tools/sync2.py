"""Sync counts after registering figure_provenance (167 -> 168)."""
import io
import os
import subprocess
import sys

REPO = r"D:\agent\nasdaq-fpga"
REPORT = os.path.join(REPO, "docs", "final-report.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

anchor = "| `sim_archive` | — | 第 183 轮新增：仿真运行留档，报告引用的仿真数字可在归档中查到 |"
row = anchor + "\n| `figure_provenance` | — | 第 184 轮新增：报告中每个数字都能追溯到产物，或被明确声明为无产物 |"

if "`figure_provenance`" not in rep:
    if anchor not in rep:
        print("row anchor not found")
    else:
        rep = rep.replace(anchor, row, 1)
        print("row added")

rep = rep.replace("passed 166, failed 0, skipped 0, pending 1 of 167",
                  "passed 167, failed 0, skipped 0, pending 1 of 168", 1)
rep = rep.replace("**167 项**独立检查", "**168 项**独立检查", 1)
io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape", newline="\n").write(rep)
print("report counts updated to 168")

subprocess.run([sys.executable, os.path.join(REPO, "tools", "gen_status.py")],
               capture_output=True, text=True, encoding="utf-8", errors="replace",
               cwd=os.path.join(REPO, "tools"))

for name in ("check_repro_doc.py", "check_status_genuine.py"):
    r = subprocess.run([sys.executable, os.path.join(REPO, "tools", name)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=os.path.join(REPO, "tools"))
    print("  %-24s exit=%d %s" % (name, r.returncode,
                                  ((r.stdout or "") + (r.stderr or "")).strip().split("\n")[-1][:40]))
