"""Where the node callables are written, importing the numbers from beside them."""

from .ranking import SHORTLIST, rank
from .settings import LIMITS

LIMIT = 8


def step(inputs, ctx):
    """One node's body, reaching the module the numbers live in."""
    return {
        **inputs,
        "ranked": rank(list(range(LIMIT))),
        "cut": SHORTLIST,
        "page": LIMITS["per_page"],
    }
