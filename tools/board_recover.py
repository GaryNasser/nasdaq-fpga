"""Deploy and verify after a board restart, safely.

Two things went wrong the last time this was done by hand:

  1. a test loaded Overlay() a SECOND time in one process; PYNQ hangs on that, and
     killing the hung process left the DMA and the overlay wedged, so the board
     stopped responding and needed a power cycle;

  2. the driver on the board went stale relative to the repository, because the
     local copy changed after the last deploy and nothing checked.

So this script:
  * copies the driver and reports both hashes, so a mismatch is visible;
  * runs exactly ONE test process, never two overlay loads in a row;
  * fails fast with a clear message if the board is not reachable.

It deliberately does not reload the overlay in-process. Each measurement is a
separate `python` invocation.

usage:  python tools/board_recover.py             deploy + verify
        python tools/board_recover.py --check     reachability only
"""
import argparse
import hashlib
import io
import os
import subprocess
import sys

BOARD = 'pynq-z2-codex'
REPO = r'D:\agent\nasdaq-fpga'
REMOTE_DIR = '/home/xilinx/overlays/nasdaq'
FILES = [
    ('vivado/out/nasdaq.bit', REMOTE_DIR + '/nasdaq.bit'),
    ('vivado/out/nasdaq.hwh', REMOTE_DIR + '/nasdaq.hwh'),
    ('board/load_overlay.py', REMOTE_DIR + '/load_overlay.py'),
]


def sh(args, timeout=120):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def md5_local(path):
    h = hashlib.md5()
    with open(os.path.join(REPO, path), 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def verdict(stdout, returncode):
    """Decide whether a recovery run succeeded.

    Returns (ok, reasons). Four conditions, all required: a clean exit, GOLDEN-OK in the
    output, no FAIL line, and no traceback. A substring test alone returned success for a run
    that printed GOLDEN-OK and then crashed - see tools/mock_board_recover.py.

    Kept as a function so tools/check_board_verdict.py can execute the SHIPPED logic against
    fabricated scenarios, rather than copying it.
    """
    out = stdout or ''
    clean_exit = (returncode == 0)
    saw_golden = 'GOLDEN-OK' in out
    saw_fail = any(line.strip().startswith(('FAIL', 'GOLDEN-FAIL'))
                   for line in out.splitlines())
    saw_traceback = 'Traceback (most recent call last)' in out
    ok = clean_exit and saw_golden and not saw_fail and not saw_traceback

    reasons = []
    if not clean_exit:
        reasons.append('remote exit %d' % returncode)
    if not saw_golden:
        reasons.append('GOLDEN-OK not printed')
    if saw_fail:
        reasons.append('a FAIL line is present')
    if saw_traceback:
        reasons.append('python traceback in the output')
    return ok, reasons


def _assert_pair_consistent():
    """Refuse to deploy a bitstream and a handoff from different builds.

    Round 2: two rebuilds "failed on hardware" because only nasdaq.bit was copied and the archived nasdaq.hwh stayed
    behind. Each file's own md5 matched its own record; the PAIR was wrong. That surfaced as a Bus error with no
    output at all - the failure mode this project has spent the most rounds on.
    """
    import glob
    import hashlib
    import json

    out = os.path.join(REPO, "vivado", "out")
    bit = os.path.join(out, "nasdaq.bit")
    hwh = os.path.join(out, "nasdaq.hwh")
    prov = os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.runs", "impl_1",
                        "BUILD-PROVENANCE.json")

    for p in (bit, hwh):
        if not os.path.exists(p):
            print("DEPLOY-REFUSED: %s is missing" % os.path.basename(p))
            return False
    if not os.path.exists(prov):
        print("DEPLOY-REFUSED: BUILD-PROVENANCE.json is missing - run tools/gen_provenance.py")
        return False

    def md5(p):
        return hashlib.md5(io.open(p, "rb").read()).hexdigest()

    want_bit = json.load(io.open(prov, encoding="utf-8")).get("bitstream_md5", "")
    got_bit = md5(bit)
    if got_bit != want_bit:
        print("DEPLOY-REFUSED: nasdaq.bit %s != provenance %s" % (got_bit[:16], want_bit[:16]))
        return False

    gens = glob.glob(os.path.join(REPO, "vivado", "workspace", "nasdaq", "nasdaq.gen", "**",
                                  "nasdaq.hwh"), recursive=True)
    if gens:
        want_hwh = md5(gens[0])
        got_hwh = md5(hwh)
        if got_hwh != want_hwh:
            print("DEPLOY-REFUSED: nasdaq.hwh %s != BD handoff %s" % (got_hwh[:16], want_hwh[:16]))
            print("  The bitstream and handoff are from DIFFERENT builds. Deploying the pair would")
            print("  program a mismatched overlay - the round-1 Bus error.")
            print("  Rebuild, or restore both files from the same archive.")
            return False

    print("PAIR-OK: bit %s / hwh %s are from the same build" % (got_bit[:12], md5(hwh)[:12]))
    return True


def main():
    if not _assert_pair_consistent():
        return 6
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    r = sh(['ssh', '-o', 'ConnectTimeout=12', BOARD, 'echo ALIVE'])
    if 'ALIVE' not in r.stdout:
        print('BOARD-UNREACHABLE')
        print('  ssh: %s' % (r.stderr.strip().splitlines()[-1:] or 'timeout'))
        print('  the board needs a power cycle before anything below can run')
        return 2
    print('board reachable')
    if a.check:
        return 0

    for local, remote in FILES:
        lh = md5_local(local)
        rr = sh(['ssh', '-o', 'ConnectTimeout=12', BOARD, 'md5sum ' + remote])
        rh = rr.stdout.split()[0] if rr.stdout.strip() else 'missing'
        if lh != rh:
            print('deploying %s' % local)
            # check=True would raise CalledProcessError out of main(), ending the run
            # in a traceback at the moment someone is watching a freshly power-cycled
            # board. Report the cause and return a distinct code instead.
            cp = subprocess.run(['scp', '-q', os.path.join(REPO, local),
                                 '%s:%s' % (BOARD, remote)],
                                capture_output=True, text=True)
            if cp.returncode != 0:
                print('DEPLOY-FAILED: scp %s -> %s (exit %d)'
                      % (local, remote, cp.returncode))
                for line in (cp.stderr or '').strip().splitlines()[:4]:
                    print('  ' + line.strip())
                return 4
            rr = sh(['ssh', BOARD, 'md5sum ' + remote])
            rh = rr.stdout.split()[0] if rr.stdout.strip() else 'missing'
        print('  %-46s %s %s' % (remote, lh[:12],
                                 'OK' if lh == rh else 'MISMATCH ' + rh[:12]))
        if lh != rh:
            return 3

    # ---- preconditions on the board -------------------------------------
    #
    # The golden run needs its input to exist. Without this probe a missing capture
    # fails inside load_overlay and the operator gets a generic non-clean exit while
    # watching a freshly power-cycled board - the worst moment to make someone debug.
    capture = '/home/xilinx/itch_loc6836.mold64'
    rr = sh(['ssh', '-o', 'ConnectTimeout=12', BOARD,
             'stat -c %s ' + capture])
    if not rr.stdout.strip().isdigit():
        print('INPUT-MISSING: %s is not on the board' % capture)
        print('  deploy it first:  scp <local>/data/itch_loc6836.mold64 '
              'xilinx@%s:%s' % (BOARD, capture))
        return 5
    remote_size = int(rr.stdout.strip())
    print('input %s  %d bytes' % (capture, remote_size))
    expected = 1237116
    if remote_size != expected:
        print('INPUT-SIZE-MISMATCH: expected %d, found %d' % (expected, remote_size))
        print('  the driver enforces this via REFERENCE_CAPTURE_SIZE and would return 6')
        return 5

    print()
    print('running the golden comparison (one process, one overlay load)')
    cmd = ('cd %s && sudo -n env XILINX_XRT=/usr '
           '/usr/local/share/pynq-venv/bin/python load_overlay.py '
           '--book --input /home/xilinx/itch_loc6836.mold64 --repeat 1'
           % REMOTE_DIR)
    r = sh(['ssh', '-o', 'ConnectTimeout=15', BOARD, cmd], timeout=600)
    for line in (r.stdout or '').splitlines():
        if any(k in line for k in ('BOOK-', 'TS-STATS', 'GOLDEN', 'FAIL',
                                   'PASS')):
            print('  ' + line.strip())
    # Four conditions, all required. A substring test alone returned success for a
    # run that printed GOLDEN-OK and then crashed - see tools/mock_board_recover.py.
    ok, _reasons = verdict(r.stdout or '', r.returncode)

    # Persist the full output. Rounds 103-104 found six headline figures with no file behind
    # them, all console output that was never saved; this is the change that prevents a repeat.
    try:
        import datetime
        import hashlib
        meas_dir = os.path.join(REPO, 'docs', 'measurements')
        os.makedirs(meas_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        rec = os.path.join(meas_dir, 'board-recover-%s.txt' % stamp)
        bit = os.path.join(REPO, 'vivado', 'out', 'nasdaq.bit')
        bit_md5 = None
        if os.path.exists(bit):
            bit_md5 = hashlib.md5(open(bit, 'rb').read()).hexdigest().upper()
        with io.open(rec, 'w', encoding='utf-8', newline='\n') as f:
            f.write('# board_recover run %s\n' % stamp)
            f.write('# host: %s\n' % BOARD)
            f.write('# command: %s\n' % cmd)
            f.write('# bitstream md5: %s\n' % (bit_md5 or 'missing'))
            f.write('# remote exit: %d\n' % r.returncode)
            f.write('# verdict: %s\n' % ('OK' if ok else 'FAIL'))
            f.write('#\n# ---- full remote stdout ----\n')
            f.write(r.stdout or '')
            if r.stderr:
                f.write('\n# ---- stderr ----\n')
                f.write(r.stderr)
        print('  output saved to %s' % os.path.relpath(rec, REPO))
    except Exception as exc:                       # never let logging break the run
        print('  WARNING: could not save the run output: %s' % exc)

    print()
    if ok:
        print('BOARD-RECOVER-OK')
    else:
        print('BOARD-RECOVER-FAIL: %s' % ', '.join(_reasons))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
