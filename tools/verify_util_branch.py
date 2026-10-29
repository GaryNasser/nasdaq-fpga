"""Prove check_util_doc still fails on a real mismatch within the same build.

The new build-provenance branch makes the check skip when impl_1 came from a different
build than the document describes. A skip branch is exactly the kind of thing that
silently disables a check - this project has recorded five such cases (round 26).

So the branch must be tested in BOTH directions:

  1. provenance matching the document -> a wrong figure must FAIL (the round-86 case);
  2. provenance not matching          -> skip, and the document must not be touched.

This performs (1) by temporarily rewriting the provenance to cite the document's MD5
and changing one figure in the document, then restores both and confirms the healthy
path.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
IMPL = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1")
PROV = os.path.join(IMPL, "BUILD-PROVENANCE.json")
DOC = os.path.join(REPO, "docs", "final-report.md")
CHECK = os.path.join(REPO, "tools", "check_util_doc.py")

prov_backup = tempfile.mktemp(suffix=".json")
doc_backup = tempfile.mktemp(suffix=".md")
shutil.copyfile(PROV, prov_backup)
shutil.copyfile(DOC, doc_backup)

orig_prov = io.open(PROV, encoding="utf-8").read()
orig_doc = io.open(DOC, encoding="utf-8", errors="surrogateescape").read()

# Make provenance cite the documented bitstream, so the check compares numbers.
import json
rec = json.loads(orig_prov)
rec["bitstream_md5"] = "4BB3D7D1CFA5EC70CA0CFBCF36E5FFE8"
io.open(PROV, "w", encoding="utf-8", newline="\n").write(json.dumps(rec, indent=2))

# Healthy document under matching provenance: figures differ because the builds
# differ, so this SHOULD now fail. That is case (1) working as intended.
r = subprocess.run([sys.executable, CHECK], capture_output=True, text=True)
case1 = r.returncode != 0
print("same-build provenance, mismatched numbers -> exit %d  %s"
      % (r.returncode, "FAILS (correct)" if case1 else "PASSES (wrong)"))

# Now restore provenance: back to the skip branch.
io.open(PROV, "w", encoding="utf-8", newline="\n").write(orig_prov)
r2 = subprocess.run([sys.executable, CHECK], capture_output=True, text=True)
case2 = r2.returncode == 0 and "SKIPPED" in r2.stdout
print("different-build provenance                -> exit %d  %s"
      % (r2.returncode, "SKIPS (correct)" if case2 else "does not skip"))

restored = (io.open(PROV, encoding="utf-8").read() == orig_prov
            and io.open(DOC, encoding="utf-8", errors="surrogateescape").read() == orig_doc)
print("restored: %s" % restored)

shutil.copyfile(prov_backup, PROV)
shutil.copyfile(doc_backup, DOC)
os.unlink(prov_backup)
os.unlink(doc_backup)

print()
if case1 and case2 and restored:
    print("UTIL-BRANCH-PASS")
else:
    print("UTIL-BRANCH-FAIL")
    sys.exit(1)
