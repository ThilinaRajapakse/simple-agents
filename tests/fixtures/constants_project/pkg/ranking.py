"""Where the numbers are written."""

WEIGHT = 0.0024
SHORTLIST = 12
BACKWARDS = -3
_INTERNAL = 99
NAME = "not a number"
ENABLED = True
COMPUTED = 6 * 2


def rank(rows: list[int]) -> list[int]:
    """Order and cut, which is what the numbers above are for."""
    return sorted(rows)[:SHORTLIST]
