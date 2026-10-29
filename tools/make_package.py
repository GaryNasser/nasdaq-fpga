"""Build the submission archive from an explicit whitelist.

The repository root holds ~90 transcript files, .wdb waveform dumps, xsim
working directories and build logs. Zipping `.` would ship all of it and bury
the four files a judge actually opens. This writes `dist/nasdaq-fpga-<date>.zip`
containing only listed paths, plus MANIFEST.txt with an md5 per member so the
archive can be checked after transfer.

    python tools/make_package.py            # build the archive
    python tools/make_package.py --dry-run  # list what would go in

Nothing here rewrites a source file; the only write is the zip itself.
"""
import argparse
import datetime
import fnmatch
import hashlib
import io
import os
import re
import sys
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(REPO, "dist")

# Explicit whitelist. Globs are matched against repo-relative POSIX paths.
INCLUDE = [
    "README.md",
    "docs/*.md",
    "docs/measurements/*.txt",
    "rtl/*.v", "rtl/*/*.v",
    "tools/*.v", "tools/*.py",
    "board/*.py",
    "vivado/out/nasdaq.bit", "vivado/out/nasdaq.hwh",
    "vivado/*.tcl", "vivado/*.xdc",
    "build_check/20261028_8FD5FA87/*",
    # The captured suite verdicts that docs/status.md quotes. Shipping them makes that
    # line checkable inside the archive instead of asking a reader to trust it.
    "build_check/verdicts-*/*",
    "data/itch_loc6836.mold64",
    "data/itch_1m.mold64",
    "specs/*.md",
    # The rendered report belongs in the archive: one file a judge opens, instead of
    # asking them to convert Markdown. Built by tools/make_report_pdf.py.
    "dist/final-report.pdf",
]

# Applied after the whitelist: generated content and scratch state.
EXCLUDE = [
    "*__pycache__*", "*.pyc", "*.wdb", "*.jou", "*.pb",
    "tools/check_*.py",          # the 301-check harness is documented, not shipped
    "tools/mutate_*.py", "tools/prove_*.py",
    "tools/audit_*.py", "tools/gen_status.py", "tools/make_package.py",
    "tools/run_checks.py", "tools/run_sims.py",
    # Every one of these is a transcript of the same inconclusive chunk sweep;
    # shipping ~100 copies of one failure adds noise, not evidence. The reason
    # DMA-to-DDR is unmeasured is stated in the report and README.
    "docs/measurements/chunk-sweep-*.txt",
]


def _rx(pattern):
    """Glob -> regex in which `*` does NOT cross `/` (fnmatch would, and did)."""
    out = []
    for ch in pattern:
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
    return re.compile("^" + "".join(out) + "$")


_CACHE = {}


def match(rel, patterns):
    for p in patterns:
        r = _CACHE.get(p)
        if r is None:
            r = _CACHE[p] = _rx(p)
        if r.match(rel):
            return True
    return False


def collect():
    picked = []
    for root, dirs, files in os.walk(REPO):
        # dist/ is walked so the built PDF can be picked up; the whitelist keeps the
        # zip files that live there out.
        dirs[:] = [d for d in dirs
                   if d not in (".git", "xsim.dir", "__pycache__", ".playwright-mcp")]
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, REPO).replace(os.sep, "/")
            if match(rel, INCLUDE) and not match(rel, EXCLUDE):
                picked.append(rel)
    return sorted(set(picked))


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = collect()
    if not files:
        print("PACKAGE-FAIL: whitelist matched nothing")
        return 1

    total = sum(os.path.getsize(os.path.join(REPO, f)) for f in files)
    print("selected %d file(s), %.1f MB" % (len(files), total / 1e6))
    if args.dry_run:
        for f in files:
            print("  %-52s %8.1f KB" % (f, os.path.getsize(os.path.join(REPO, f)) / 1024))
        return 0

    os.makedirs(DIST, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    out = os.path.join(DIST, "nasdaq-fpga-%s.zip" % stamp)

    manifest = ["# md5  size  path", ""]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in files:
            full = os.path.join(REPO, rel)
            z.write(full, "nasdaq-fpga/" + rel)
            manifest.append("%s  %10d  %s" % (md5_of(full),
                                              os.path.getsize(full), rel))
        z.writestr("nasdaq-fpga/MANIFEST.txt", "\n".join(manifest) + "\n")

    print("written %s (%.1f MB)" % (os.path.relpath(out, REPO),
                                    os.path.getsize(out) / 1e6))
    bit = os.path.join(REPO, "vivado", "out", "nasdaq.bit")
    print("bitstream in the archive: %s" % (md5_of(bit).upper() if os.path.exists(bit) else "missing"))
    print("PACKAGE-OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
