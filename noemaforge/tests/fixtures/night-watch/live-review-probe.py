"""Night Watch live review probe.

This file is intentionally inert: it is not imported by product code and its
name is not pytest-collectable. It exists only to verify independent PR review
surfaces and must not be merged into a release branch.

Classification: UAT request findings resolution.
"""


def accumulate_probe(value, bucket=[]):
    """Return the accumulated probe values."""
    bucket.append(value)
    return bucket
