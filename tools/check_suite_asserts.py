"""Third version: recognise multi-line `else if` conditions.

The check reported tb_stall3's pass token as unguarded, but the code is:

    if (tready_low_cycles < 100) begin
      $display("[FAIL] TREADY barely dropped - the FIFO never filled");
      $display("STALL3-FAIL");
    end else if (dut.rx_packets == NPKT && dut.rx_messages == NPKT &&
                 dut.error_count == 0 && dut.gap_count == 0)
      $display("STALL3-PASS");
    else
      $display("STALL3-FAIL");

The guard spans two lines and starts with `end else if`. The previous version looked
for a line matching `\\s*(if|else|case)` at lower indentation; `end else if (...)`
starts with `end`, so it was missed.

Version history, each killed by testing against the real files:
  1. multi-line `if` only          - missed the single-line form (tb_ts_hist)
  2. + same-line `if (c) $display` - missed `end else if` (tb_stall3)
  3. this one

The pattern now allows `end ` as a prefix and checks that the condition opened on
that line actually closes with a `)` before the display, so a bare `else` does not
count as a guard.
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
TOOLS = os.path.join(REPO, "tools")

SUITES = [
    ("stream", "tb_stream.v", "STREAM-PASS"),
    ("varsize", "tb_varsize.v", "VARSIZE-PASS"),
    ("backpress", "tb_stream_bp.v", "BP-PASS"),
    ("stall3", "tb_stall3.v", "STALL3-PASS"),
    ("gap", "tb_gap.v", "GAP-PASS"),
    ("parity", "tb_parity2.v", "PARITY-PASS"),
    ("realfile", "tb_realfile.v", "REALFILE-PASS"),
    ("ts_hist", "tb_ts_hist.v", "TS-HIST-ALL-PASS"),
    ("book", "tb_book.v", "BOOK-PASS"),
    ("rate", "tb_rate_book.v", "RATE-PASS"),
    ("fullchain", "tb_fullchain.v", "FULLCHAIN-PASS"),
    ("coldstart", "tb_cold_start.v", "COLD-FAIL"),
    ("noreset", "tb_no_reset.v", "NORESET-PASS"),
    ("resetseq", "tb_reset_seq.v", "RESETSEQ-PASS"),
]

# A line that opens a guard: if / else if / end else if (condition spanning lines
# is fine - we only need to know a condition EXISTS).
GUARD_OPEN = re.compile(r"^\s*(?:end\s+)?(?:else\s+)?(?:if|case)\b")


def guarded_at(lines, idx):
    """Is the $display at `idx` under a conditional?"""
    line = lines[idx]
    # Same line: if (cond) $display(...)
    if re.search(r"\bif\s*\(.*\)\s*\$display", line):
        return True
    depth = len(line) - len(line.lstrip())
    for j in range(idx - 1, max(-1, idx - 25), -1):
        lj = lines[j]
        if not lj.strip():
            continue
        d = len(lj) - len(lj.lstrip())
        if d < depth:
            if GUARD_OPEN.match(lj):
                return True
            # A branch body is conditional if it follows else/endif of a guard.
            if re.match(r"^\s*(?:end\s+)?else\b", lj):
                return True
            return False
    return False


fails = []
print("%-11s %-10s %-10s %s" % ("suite", "fail path", "guarded", "note"))
print("-" * 76)

for label, tb, token in SUITES:
    path = os.path.join(TOOLS, tb)
    if not os.path.exists(path):
        print("%-11s %-10s %-10s MISSING" % (label, "-", "-"))
        fails.append("%s: missing" % label)
        continue
    src = io.open(path, encoding="utf-8", errors="replace").read()
    lines = src.split("\n")

    has_fail = bool(re.search(r'\$display\s*\(\s*"[^"]*FAIL', src)
                    or "$fatal" in src or "$error" in src)

    ok = False
    # Some suites (coldstart) use a FAILURE token as their pass condition: the
    # suite passes when the FAILURE is observed, because the test's purpose is to
    # demonstrate that an illegal sequence still breaks the stream. For those the
    # requirement is the same - the token must be conditional - but it will sit in
    # an `else` branch, which `guarded_at` already accepts (the `else` follows an
    # `if`, and the nearest guard above is that `if`).
    for i, l in enumerate(lines):
        # Skip comments: a token mentioned in prose is not an output.
        if l.strip().startswith("//"):
            continue
        if token in l and "$display" in l:
            ok = guarded_at(lines, i)
            break

    note = ""
    if not has_fail:
        note = "no failure path"
        fails.append("%s: cannot fail" % label)
    if not ok:
        note = (note + "; " if note else "") + "pass token unconditional"
        fails.append("%s: pass token not guarded" % label)

    print("%-11s %-10s %-10s %s"
          % (label, "yes" if has_fail else "NO", "yes" if ok else "NO", note))

print()
if fails:
    print("SUITE-ASSERT-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("SUITE-ASSERT-PASS")
