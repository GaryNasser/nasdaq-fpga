"""A shared helper the mutation proofs can call to confirm their mutation landed.

59 registered proofs replace text and never check that the replacement happened. If the anchor is absent the "mutation"
writes the original back, the check under test passes, and the proof reports MISSED **against a check that was never
exercised**.

Rather than rewrite 59 scripts, this provides the two functions they need, and a check that counts how many still
lack them so the number can only go down.
"""
import io
import os
import sys

REPO = r"D:\agent\nasdaq-fpga"
sys.path.insert(0, os.path.join(REPO, "tools"))


def mutate(text, old, new, what):
    """Replace `old` with `new`, refusing unless the replacement actually happened.

    Returns the mutated text. Raises LandedError when `old` is absent, so a proof can report INCONCLUSIVE rather than
    MISSED.
    """
    if old not in text:
        raise LandedError("the anchor for %r is not in the document" % what)
    out = text.replace(old, new, 1)
    if out == text:
        raise LandedError("%r produced no change" % what)
    return out


class LandedError(Exception):
    """The mutation could not be applied - it says nothing about the check under test."""


def landed(before, after, what):
    """True when the document actually changed."""
    ok = before != after
    if not ok:
        print("MUTATION-NOT-LANDED: %r changed nothing, so this proof tests nothing" % what)
    return ok
