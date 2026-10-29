"""Mutations for the runbook-fact check.

The failure this prevents: the operator follows a runbook whose numbers no longer match the
code - wrong capture size, wrong exit code meaning, a bitstream MD5 that is not the one
being deployed.

Mutations:
  1. change the capture size in the runbook      -> must FAIL
  2. change the bitstream MD5 in the runbook     -> must FAIL
  3. drop an exit-code row                       -> must FAIL
  4. remove the shipped-vs-current note          -> must FAIL
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

DOC = r"D:\agent\nasdaq-fpga\docs\RUNBOOK.md"
CHECK = r"D:\agent\nasdaq-fpga\tools\check_runbook_facts.py"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(DOC, backup)
original = io.open(DOC, encoding="utf-8").read()

MUTATIONS = [
    ("wrong capture size", original.replace("1,237,116", "1,237,999")),
    ("wrong bitstream MD5",
     # Round 251: 0ADD0828 is the PREVIOUSLY DEPLOYED build, correctly present as history. The current md5 is
     # 0BF5C1B0; breaking THAT is the mutation that tests whether the runbook tracks the shipped bitstream.
     original.replace("8FD5FA87BAFA17055549A3E8BA201F6B", "DEADBEEFCAFEBABE0000000000000000")),
    ("exit code row removed", original.replace("| 5 | 板上输入缺失或尺寸不符 | 按提示 scp 该文件 |\n", "")),
    ("shipped note removed",
     original.replace("来自另一份 bitstream", "来自某个 bitstream")
     .replace("不重现已发布的数字", "重现已发布的数字")),
]

results = []
for name, mutated in MUTATIONS:
    landed = mutated != original
    io.open(DOC, "w", encoding="utf-8", newline="\n").write(mutated)
    r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    caught = r.returncode != 0
    results.append((name, landed, caught))
    print("%-26s landed=%-5s exit=%d %s"
          % (name, landed, r.returncode, "CAUGHT" if caught else "MISSED"))
    io.open(DOC, "w", encoding="utf-8", newline="\n").write(original)

restored = io.open(DOC, encoding="utf-8").read() == original
print("restored: %s" % restored)

r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
print("healthy exit code: %d" % r.returncode)

shutil.copyfile(backup, DOC)
os.unlink(backup)

print()
if all(l and c for _, l, c in results) and restored and r.returncode == 0:
    print("RUNBOOK-FACT-MUTATION-PASS")
else:
    print("RUNBOOK-FACT-MUTATION-FAIL")
    sys.exit(1)
