"""Confirm check_gbe_claims rejects the ORIGINAL round-30 sentence.

The sentence that was wrong:

    可确定的是：模块级 TB 与板上单包测量都表明 PL 侧字节处理能力远高于 1 GbE
    （见 §6 的 T1），瓶颈完全在入口机制。

It asserts a margin over 1 GbE and cites T1 - a 299 ns/message measurement that works
out to 0.75x of line rate. No byte rate, no multiplier, no number of any kind in the
sentence: the claim rested entirely on a reference whose value contradicts it.

Note carefully what this test proves and what it does not. The check requires that a
margin claim carry arithmetic. It does NOT verify the arithmetic is right - that is a
human judgement, which is why the corrected text shows both the 1.52x port figure and
the 0.75x measured figure with their derivations. A checker that claimed to validate
the direction of the comparison would be claiming more than a regex can deliver.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

DOC = r"D:\agent\nasdaq-fpga\docs\final-report.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_gbe_claims.py"

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(DOC, backup)

# Round 252: registered proofs run every suite; a killed run must not leave the report rewritten.
import atexit as _atexit
_atexit.register(lambda _d=DOC, _s=backup: os.path.exists(_s) and shutil.copyfile(_s, _d))

original = io.open(DOC, encoding="utf-8", errors="surrogateescape").read()

PLANT = ("\n可确定的是：模块级 TB 与板上单包测量都表明 PL 侧字节处理能力远高于 1 GbE"
         "（见 §6 的 T1），瓶颈完全在入口机制。\n")

mutated = original + PLANT
io.open(DOC, "w", encoding="utf-8", errors="surrogateescape",
        newline="\n").write(mutated)

landed = "远高于 1 GbE" in io.open(DOC, encoding="utf-8",
                                   errors="surrogateescape").read()
print("mutation landed: %s" % landed)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("check exit code: %d" % r.returncode)

shutil.copyfile(backup, DOC)
os.unlink(backup)
restored = io.open(DOC, encoding="utf-8", errors="surrogateescape").read() == original
print("restored: %s" % restored)

r2 = subprocess.run([sys.executable, CHECK], capture_output=True, text=True, encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r2.returncode)

print()
if landed and r.returncode != 0 and restored and r2.returncode == 0:
    print("GBE-MUTATION-PASS")
else:
    print("GBE-MUTATION-FAIL")
    sys.exit(1)
