"""One way to record a board session, so no measurement can go unarchived.

Round 191 found only two tools write transcripts (`board_recover.py`, `chunk_sweep.py`). Every other board-facing
script leaves nothing, so a future round asking "did this ever produce a number" has no answer - which is exactly
the question rounds 182-191 spent ten rounds on for OTHER figures.

### What this provides

    archive(name, argv, stdout, stderr, exit_code, bitstream=None)  -> path

Writes `docs/measurements/<name>-<timestamp>.txt` with a header naming the command, the bitstream under test, the
exit code, and then the full output. The header fields are the ones a later audit needs:

    which tool, with what arguments, against which bitstream, what it said, and whether it succeeded

### Why a module and not a convention

A convention is what produced two tools out of many. A function that takes the output and stores it is one line
to call, and `check_board_logging` can then require every board-facing script to call it.
"""
import datetime
import io
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEAS = os.path.join(REPO, "docs", "measurements")


def archive(name, argv, stdout, stderr="", exit_code=0, bitstream=None, extra=None):
    """Record one run. Returns the path written.

    Never raises: a failure to archive must not fail the measurement it was recording.
    """
    try:
        os.makedirs(MEAS, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(MEAS, "%s-%s.txt" % (name, stamp))

        lines = []
        lines.append("# %s run %s" % (name, stamp))
        if argv:
            lines.append("# argv: %s" % (argv if isinstance(argv, str) else " ".join(map(str, argv))))
        if bitstream:
            lines.append("# bitstream md5: %s" % bitstream)
        lines.append("# exit: %s" % exit_code)
        if extra:
            for k, v in extra.items():
                lines.append("# %s: %s" % (k, v))
        lines.append("#")
        lines.append("# ---- transcript ----")
        lines.append((stdout or "").rstrip())
        if stderr:
            lines.append("")
            lines.append("# ---- stderr ----")
            lines.append((stderr or "").rstrip())

        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        return path
    except Exception:
        return None


def current_bitstream_md5():
    """The bitstream under test, so a transcript says which design produced it."""
    import hashlib
    p = os.path.join(REPO, "vivado", "out", "nasdaq.bit")
    try:
        return hashlib.md5(io.open(p, "rb").read()).hexdigest()
    except OSError:
        return None


if __name__ == "__main__":
    # Self-test: write one and confirm it round-trips its header fields.
    p = archive("selftest", ["--demo"], "line one\nline two\n", "", 0,
                bitstream=current_bitstream_md5(), extra={"purpose": "record module self-test"})
    body = io.open(p, encoding="utf-8").read()
    print("wrote %s" % os.path.basename(p))
    for want in ("# selftest run", "# argv: --demo", "# exit: 0", "line one"):
        print("  %-16s %s" % (want.strip("# "), want in body))
    os.unlink(p)
    print("self-test file removed")
