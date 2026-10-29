import datetime
"""Run the RTL simulation suites and report a single verdict.

The static contract suite (run_checks.py) covers constants, addresses and the
driver. It does not compile or simulate anything. The behavioural suites -
STREAM, VARSIZE, BP, STALL3, GAP, PARITY, REALFILE, BOOK, TS-HIST and the two
full-chain tests - were run by hand, one xvlog/xelab/xsim triad at a time.

This runs them. Each entry names the sources it needs and the token its verdict
prints, so a silent failure (no token at all) is caught as well as an explicit
FAIL.

The three img.hex-dependent tests are run with their own working directory
populated from a freshly generated image, because img.hex is reused across
datasets and a stale one produces misleading all-zero results (round 68).
"""
import io
import os
import re
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RTL = os.path.join(REPO, "rtl", "itch")
TOOLS = os.path.join(REPO, "tools")
TMPDIR = os.environ.get("TEMP", os.environ.get("TMP", "/tmp"))
WORK = os.path.join(TMPDIR, "nasdaq_simsuite")
REALFILE_WORK = os.path.join(TMPDIR, "nasdaq_realfile")

VIVADO_BIN = os.environ.get("VIVADO_BIN", r"D:\Xilinx\Vivado\2024.1\bin")

env = dict(os.environ)
env["PATH"] = VIVADO_BIN + os.pathsep + env.get("PATH", "")

REASM = [os.path.join(RTL, "mold64_reasm.v")]
PARSE_BOOK = [os.path.join(RTL, "itch_parse.v"), os.path.join(RTL, "order_book.v")]
CHAIN = [os.path.join(RTL, "mold64_reasm.v"), os.path.join(RTL, "itch_parse.v"),
         os.path.join(RTL, "order_book.v"), os.path.join(RTL, "ts_hist.v")]

# (label, tb file, sources, expected verdict token, needs img.hex)
# What a suite's token means.
#
#   KIND_PASS      the token is a success verdict.
#   KIND_EXPECTED  the token is an EXPECTED failure. The test exists to show that a
#                  bad sequence really does corrupt the stream, so observing that
#                  failure is the pass condition. Declared explicitly because it looks
#                  identical to a broken suite in the output.
KIND_PASS = "pass"
KIND_EXPECTED = "expected-failure"

SUITES = [
    ("stream",   "tb_stream.v",    REASM,          "STREAM-PASS", True, KIND_PASS),
    ("ctrl_regs","tb_ctrl_regs.v", [os.path.join(REPO, "rtl", "ctrl_regs.v")], "TB-ALL-PASS", True, KIND_PASS),
    ("varsize",  "tb_varsize.v",   REASM,          "VARSIZE-PASS", True, KIND_PASS),
    ("backpress","tb_stream_bp.v", REASM,          "BP-PASS", True, KIND_PASS),
    ("stall3",   "tb_stall3.v",    REASM,          "STALL3-PASS", True, KIND_PASS),
    ("gap",      "tb_gap.v",       REASM,          "GAP-PASS", True, KIND_PASS),
    # tb_parity2 prints PARITY-TOTAL on BOTH pass and fail, so matching that
    # token would pass a broken run. Require the errs=0 field specifically.
    ("parity",   "tb_parity2.v",   REASM,          "PARITY-PASS", True, KIND_PASS),
    ("realfile", "tb_realfile.v",  REASM,          "REALFILE-PASS", True, KIND_PASS),
    ("emit_bytes","tb_emit_bytes.v", REASM,          "EMIT-PASS", True, KIND_PASS),
    ("one_tlast", "tb_one_tlast2.v",REASM,          "ONE2-PASS", True, KIND_PASS),
    ("empty",     "tb_empty.v",    REASM,          "EMPTY-PASS", True, KIND_PASS),
    ("truncated", "tb_truncated.v",REASM,          "TRUNC-PASS", True, KIND_PASS),
    ("disable",   "tb_disable.v",  REASM,          "DISABLE-PASS", True, KIND_PASS),
    ("book_edge", "tb_book_edge.v",PARSE_BOOK,    "EDGE-PASS", True, KIND_PASS),
    ("ts_pair",   "tb_repro_pair.v",[os.path.join(RTL, "ts_hist.v")], "PAIR-PASS",  True, KIND_PASS),
    ("sticky",   "tb_sticky.v",    REASM,          "STICKY-PASS", True, KIND_PASS),
    ("ts_hist",  "tb_ts_hist.v",   [os.path.join(RTL, "ts_hist.v")], "TS-HIST-ALL-PASS", False, KIND_PASS),
    ("book",     "tb_book.v",      PARSE_BOOK,     "BOOK-PASS", True, KIND_PASS),
    ("rate",     "tb_rate_book.v", PARSE_BOOK,     "RATE-PASS", True, KIND_PASS),
    # Round 7: the level_table off-by-one. LEVELS=256 with a >= LEVELS-1 full test meant index 255
    # was never written; the board showed level_cnt=255 and the declared capacity was unreachable.
    ("levels",   "tb_book_levels.v", [os.path.join(RTL, "order_book.v")], "BOOK-LEVELS-PASS", False, KIND_PASS),
    # Round 8: the ORDER map edge. Direct-mapped, so it never fills - but a collision replaces an
    # entry and order_cnt does not decrement, which its documented meaning says it should.
    ("orders",   "tb_book_orders.v", [os.path.join(RTL, "order_book.v")], "BOOK-ORDERS-PASS", False, KIND_PASS),
    ("fullchain","tb_fullchain.v", CHAIN,          "FULLCHAIN-PASS", True, KIND_PASS),
    # Reset/enable ordering. tb_cold_start reproduces the board defect and is
    # EXPECTED to fail, so its token is the failure text: seeing it means the
    # illegal sequence still breaks the stream, which is the documented
    # behaviour. tb_no_reset and tb_reset_seq must parse the stream.
    ("coldstart","tb_cold_start.v", REASM,         "COLD-FAIL", True, KIND_EXPECTED),
    ("noreset",  "tb_no_reset.v",   REASM,         "NORESET-PASS", True, KIND_PASS),
    ("resetseq", "tb_reset_seq.v",  REASM,         "RESETSEQ-PASS", True, KIND_PASS),
    # itch_parse alone, on a stream unlike the shipped capture: unknown ITCH
    # types of odd lengths must not desynchronise the framing.
    # Round 122: the session byte-0 window. The first accepts a bad first packet (a known
    # defect, recorded here so a fix makes it fail); the second shows later packets are
    # rejected, which bounds the defect to the window before the read pipeline is loaded.
    ("session_bad",  "tb_session_bad.v",  REASM, "BAD-PROBE-ERROR-COUNTED", True, KIND_PASS),
    ("session_scope","tb_session_bad2.v", REASM, "BAD2-PROBE-COLDSTART-ONLY", True, KIND_PASS),
    ("false_sync",   "tb_false_sync.v",  REASM, "FS-PROBE-FAIL-FALSE-SYNC", True, KIND_EXPECTED),
    ("gap_check",    "tb_gap_check.v",   REASM, "GAP-CHK-PASS", True, KIND_PASS),
    ("large_pkt",    "tb_pkt_size.v",    REASM, "SIZE-FAIL-ERR-4", True, KIND_EXPECTED),
    ("aligned_burst","tb_aligned_burst.v", REASM, "ALIGNED-PASS", True, KIND_PASS),
    ("align_sweep",  "tb_align_sweep.v", REASM, "SWEEP-PASS", True, KIND_PASS),
    ("pause_test",   "tb_pause_test.v",  REASM, "PAUSE-NO-EFFECT", True, KIND_PASS),
    ("cold_window",  "tb_coldstart.v",   REASM, "COLD-DIAG-FAIL-XWINDOW", True, KIND_EXPECTED),
    ("pause_sweep",  "tb_pause_sweep.v", REASM, "PSWEEP-NONE-BROKE", True, KIND_PASS),
    ("len_vs_gap",    "tb_len_vs_gap.v",   REASM, "LVG-DONE", True, KIND_PASS),
    ("unknown",  "tb_unknown_types.v", [os.path.join(RTL, "itch_parse.v")], "UNKNOWN-PASS", False, KIND_PASS),
]


# Round 183: archive every simulator run's output.
#
# Round 182 found ten headline measurements with nothing in the repository to back them, because this script
# matched the PASS marker and discarded the rest. A figure quoted later could only be quoted from memory.
#
# `sh()` is the single choke point for every xvlog/xelab/xsim call, so archiving here covers all of them. Files
# land in build_check/sim_runs/<timestamp>/ one per invocation, and the newest 20 directories are kept.
_RUN_DIR = os.path.join(REPO, "build_check", "sim_runs",
                        datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
_run_seq = [0]


def _archive(cmd, out_text):
    os.makedirs(_RUN_DIR, exist_ok=True)
    _run_seq[0] += 1
    name = "%03d_%s.log" % (_run_seq[0], str(cmd).split()[0][:24].replace("/", "_").replace("\\", "_"))
    try:
        with io.open(os.path.join(_RUN_DIR, name), "w", encoding="utf-8", newline="\n") as f:
            f.write("# command: %s\n" % cmd)
            f.write("# cwd: %s\n" % REPO)
            f.write(out_text)
    except Exception:
        pass          # archiving must never fail a simulation run


def _prune_runs(keep=20):
    try:
        dirs = sorted(d for d in os.listdir(os.path.dirname(_RUN_DIR))
                      if os.path.isdir(os.path.join(os.path.dirname(_RUN_DIR), d)))
        for d in dirs[:-keep]:
            shutil.rmtree(os.path.join(os.path.dirname(_RUN_DIR), d), ignore_errors=True)
    except Exception:
        pass


def sh(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace',
                       shell=True, env=env)
    _archive(cmd, (r.stdout or "") + (r.stderr or ""))
    return r


def build_image():
    """Generate img.hex via the project's own generator."""
    r = sh("%s %s" % (sys.executable, os.path.join(TOOLS, "run_realfile.py")), REPO)
    # The image is BUILT if run_realfile.py produced one; whether the design then passes is a
    # separate question.  After round 148 the end-of-stream shortfall makes the verdict
    # REALFILE-FAIL while the image is still generated correctly.
    ok = ("REALFILE-PASS" in r.stdout or "REALFILE-FAIL" in r.stdout)
    return ok, r.stdout


print("=" * 74)
print("RTL simulation suite")
print("=" * 74)

os.makedirs(WORK, exist_ok=True)
src_img = os.path.join(REALFILE_WORK, "img.hex")

# Always regenerate. The old code skipped generation when a previous run's image was still
# in TEMP, so a stale image could be reused after the capture changed - the same staleness
# the build provenance work fixed for bitstreams.
ok, out = build_image()
print("generating img.hex ... %s" % ("OK" if ok else "FAILED"))
if not ok or not os.path.exists(src_img):
    # Three suites depend on this image. Running them anyway produces a trio of failures
    # whose cause is not visible, and the operator has to work backwards to "the data file
    # is missing". Stop here and say so.
    print()
    print("  img.hex was not generated, so tb_realfile / tb_book / tb_rate_book cannot run.")
    if not os.path.exists(os.path.join(REPO, "data", "itch_loc6836.mold64")):
        print("  data/itch_loc6836.mold64 is missing - build it with the steps in")
        print("  docs/final-report.md section 9.2.")
    print()
    print(out[-800:])
    print()
    print("SIMSUITE-FAIL (no test image)")
    sys.exit(1)

results = []
for label, tb, sources, token, needs_img, kind in SUITES:
    tbpath = os.path.join(TOOLS, tb)
    if not os.path.exists(tbpath):
        print("[SKIP] %-10s testbench not found: %s" % (label, tb))
        results.append((label, "SKIP"))
        continue
    # Fresh directory per suite so nothing leaks between runs.
    d = os.path.join(WORK, label)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    if needs_img and os.path.exists(src_img):
        shutil.copy(src_img, os.path.join(d, "img.hex"))

    r = sh("xvlog.bat " + " ".join('"%s"' % s for s in sources) + ' "%s"' % tbpath, d)
    if r.returncode != 0:
        print("[FAIL] %-10s compile error" % label)
        for line in r.stdout.splitlines():
            if "ERROR" in line:
                print("       | " + line.strip())
                break
        results.append((label, "FAIL"))
        continue
    r = sh("xelab.bat -debug typical %s -s %s" % (tb[:-2], tb[:-2]), d)
    if r.returncode != 0:
        print("[FAIL] %-10s elaboration error" % label)
        results.append((label, "FAIL"))
        continue
    r = sh("xsim.bat %s -runall" % tb[:-2], d)

    # A suite passes only if the token appeared AND the simulation really ended
    # cleanly. Checking the token alone let a testbench print PASS and then trip a
    # $fatal be recorded as a pass - demonstrated by tools/tb_trap.v, where xsim
    # prints "Fatal:" yet still exits 0.
    saw_token = token in r.stdout
    clean_exit = (r.returncode == 0)
    # For an EXPECTED-failure suite the design is supposed to misbehave, so an
    # ERROR/Fatal line is not automatically a failure - provided it belongs to the
    # suite's own expected-failure vocabulary. Anything else still fails.
    fatal_hits = re.findall(r"^(Fatal|ERROR):(.*)$", r.stdout, re.M)
    if kind == KIND_EXPECTED:
        expected_words = re.compile(r"(COLD|expected|intentional)", re.I)
        fatal = any(not expected_words.search(msg) for _, msg in fatal_hits)
    else:
        fatal = bool(fatal_hits)
    finished = ("$finish called" in r.stdout
                or "Simulation completed" in r.stdout
                or "normal end" in r.stdout.lower())
    got = saw_token and clean_exit and not fatal and finished

    tag = "" if kind == KIND_PASS else "  (expected failure)"
    print("[%s] %-10s %s%s"
          % ("PASS" if got else "FAIL", label, token, tag))
    if not got:
        reasons = []
        if not saw_token:
            reasons.append("token not printed")
        if not clean_exit:
            reasons.append("xsim exit %d" % r.returncode)
        if fatal:
            reasons.append("Fatal/ERROR in output")
        if not finished:
            reasons.append("simulation did not reach $finish")
        print("       | " + ", ".join(reasons))
        tail = [l.strip() for l in r.stdout.splitlines() if l.strip()][-4:]
        for line in tail:
            print("       | " + line)
    results.append((label, "PASS" if got else "FAIL"))

print("=" * 74)
passed = sum(1 for _, s in results if s == "PASS")
failed = [l for l, s in results if s == "FAIL"]
skipped = [l for l, s in results if s == "SKIP"]
print("passed %d, failed %d, skipped %d of %d"
      % (passed, len(failed), len(skipped), len(results)))
if failed:
    print("failed: %s" % ", ".join(failed))
print("SIMSUITE-PASS" if not failed else "SIMSUITE-FAIL")
sys.exit(0 if not failed else 1)
