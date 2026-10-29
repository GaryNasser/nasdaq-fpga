"""Four checks were proven with throwaway scripts and are listed as unproven again.

    ctrl_sequence       round 87: CTRL 0x1 -> 0x3          (temporary script, deleted)
    clock_docs          round 86: a live 200 MHz claim     (temporary script, deleted)
    bit_repro           round 84: edit ts_hist.v           (temporary script, deleted)
    provenance_current  round 84: same edit                (temporary script, deleted)

The ledger rebuilds from files that exist, so it correctly reports them as unproven - a claim
in a log entry is not a harness. That is the ledger doing its job.

What it exposes is my own habit: I prove a check with a scratch file, confirm the result, then
delete the file. The fact is true but unreproducible - exactly the `hand-run once` category,
except I never recorded it as such because the scripts are gone.

The fix is to make these permanent proofs, and to keep them small. Four checks, one script,
each mutation a few lines.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")
OB = os.path.join(REPO, "rtl", "itch", "order_book.v")
TS = os.path.join(REPO, "rtl", "itch", "ts_hist.v")
DRV = os.path.join(REPO, "board", "load_overlay.py")
REPORT = os.path.join(REPO, "docs", "final-report.md")
LOG = os.path.join(REPO, "docs", "bringup-defects.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run(check):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, check)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


CHECKS = ["check_ctrl_sequence.py", "audit_clock_docs.py", "check_bit_repro.py",
          "check_provenance_current.py"]

print("baseline")
for c in CHECKS:
    rc, out = run(c)
    tail = [l for l in out.splitlines() if l.strip()][-1:]
    print("  %-30s exit=%d  %s" % (c, rc, tail[0][:46] if tail else ""))
print()

cases = []

# 1. ctrl_sequence: CTRL 0x1 -> 0x3 outside the legacy branch.
drv = io.open(DRV, encoding="utf-8", errors="replace").read()
m = re.search(r"\.write\(\s*REG_M64_CTRL\s*,\s*0x1\s*\)", drv)
if m:
    cases.append(("ctrl_sequence: 0x1 -> 0x3", DRV,
                  drv[:m.start()] + ".write(REG_M64_CTRL, 0x3)" + drv[m.end():],
                  "check_ctrl_sequence.py", "utf-8", "replace"))

# 2. clock_docs: a live 200 MHz claim in the report.
rep = io.open(REPORT, encoding="utf-8", errors="surrogateescape").read()
cases.append(("clock_docs: live 200 MHz claim", REPORT,
              rep + "\n\n设计在本板上运行于 200 MHz。\n", "audit_clock_docs.py",
              "utf-8", "surrogateescape"))

# 3 and 4. bit_repro / provenance_current: change one RTL line.
ts = io.open(TS, encoding="latin-1").read()
# MUTATE-ASSERT (round 204): find an assignment that EXISTS and prove the edit changed the text.
# The old target `clear_idx <= clear_idx + 1'b1` was removed in round 165, so the regex stopped
# matching, the case was silently skipped, and the proof failed for a reason unrelated to the check.
m = None
for _pat in (r"delta_hold\s*<=\s*delta64_r\[31:0\]",          # the round-201 carrier, if present
             r"clear_idx\s*<=\s*\{HIST_BIN_W\{1'b0\}\}",      # the histogram clear
             r"count_delta\s*<=\s*count_delta\s*\+\s*64'd1"):  # the counter
    m = re.search(_pat, ts)
    if m:
        break

if not m:
    print("MUTATE-ASSERT: no editable assignment found in ts_hist.v - the proof cannot run")
    raise SystemExit("PERMANENT-PROOF-FAIL (mutation target missing)")

_hit = m.group(0)
if "1'b0" in _hit:
    _rep = _hit.replace("1'b0", "1'b1")
elif "1'b1" in _hit:
    _rep = _hit.replace("1'b1", "1'b0")
elif "64'd1" in _hit:
    _rep = _hit.replace("64'd1", "64'd2")
else:
    _rep = _hit + " "
# A comment-only edit is deliberately ignored by check_bit_repro (round 33), so the mutation
# must change CODE. Assert that it did.
if _rep.strip() == _hit.strip():
    print("MUTATE-ASSERT: the edit did not change code")
    raise SystemExit("PERMANENT-PROOF-FAIL (comment-only mutation is invisible by design)")
edit = ts[:m.start()] + _rep + ts[m.end():]
if edit == ts:
    print("MUTATE-ASSERT: the edit did not change the text")
    raise SystemExit("PERMANENT-PROOF-FAIL (mutation did not apply)")

print("  mutation applied to: %s" % m.group(0)[:48])
cases.append(("bit_repro: RTL edited", TS, edit, "check_bit_repro.py",
              "latin-1", "replace"))
cases.append(("provenance_current: RTL edited", TS, edit,
              "check_provenance_current.py", "latin-1", "replace"))

results = []
for name, path, mutated, check, enc, err in cases:
    orig = io.open(path, encoding=enc, errors=err).read()
    if mutated == orig:
        print("%-36s NOT APPLIED" % name)
        continue
    bk = tempfile.mktemp(suffix=os.path.splitext(path)[1])
    shutil.copyfile(path, bk)
    try:
        io.open(path, "w", encoding=enc, errors=err, newline="\n").write(mutated)
        rc, out = run(check)
        caught = rc != 0
        results.append((name, caught))
        print("%-36s exit=%d %s" % (name, rc, "CAUGHT" if caught else "MISSED"))
        if not caught:
            for l in [x for x in out.splitlines() if x.strip()][-2:]:
                print("      %s" % l[:84])
    finally:
        shutil.copyfile(bk, path)
        os.unlink(bk)

print()
for c in CHECKS:
    rc, _ = run(c)
    print("  %-30s exit=%d (restored)" % (c, rc))

print()
if results and all(c for _, c in results):
    sys.exit(0)
print("PERMANENT-PROOF-FAIL")
sys.exit(1)
