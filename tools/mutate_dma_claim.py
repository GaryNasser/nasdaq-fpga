"""Confirm check_dma_claim distinguishes an asserted claim from a quoted one.

Mutations:
  1. add an ASSERTED claim outside any quotation    -> must FAIL
  2. remove the S2MM disclosure                     -> must FAIL
  3. remove the chunk-sweep alternative             -> must FAIL
  4. (control) the quoted-and-negated text stays    -> must PASS
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPORT = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_dma_claim.py"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(REPORT, backup)
original = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()

MUTATIONS = [
    ("assert the claim", original.replace(
        "> **关于 DMA→DDR 吞吐这个待办项（第 54 轮更正）**：",
        "> **关于 DMA→DDR 吞吐**：上电后一次测量即可关闭。\n"
        "> **关于 DMA→DDR 吞吐这个待办项（第 54 轮更正）**：", 1)),
    ("remove the S2MM disclosure", original.replace(
        "`c_include_s2mm {0}`（S2MM 未启用）", "某个配置项", 1)),
    ("remove the alternative", original.replace(
        "改变 DMA 分块大小并测量速率变化", "做一次测量", 1)
        .replace("分块大小并测量", "测量", 1)),
]

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-28s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(REPORT, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(original)

restored = io.open(REPORT, encoding="utf-8",
                   errors="surrogateescape").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d (quoted claim must still pass)" % r.returncode)

shutil.copyfile(backup, REPORT)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("DMA-CLAIM-MUTATION-PASS")
else:
    print("DMA-CLAIM-MUTATION-FAIL")
    sys.exit(1)
