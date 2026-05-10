"""Agreement statistics: Cohen kappa, Fleiss kappa, Pearson r, Spearman rho.

Pure stdlib (no numpy / scipy dep); inputs are small (n_labels < 10k in M4).
All four functions return None when there are not enough observations or all
observations collapse to one value (variance / chance-agreement floor).

Conventions
-----------
- Scores are coerced to ints for κ (κ requires categorical agreement).
  Fractional scores are rounded to nearest int — fine for the 1-5 / 0-1
  scales we ship in M4.
- Pearson / Spearman take floats; tied ranks share the average rank
  (standard "fractional" tie-breaking, matches scipy default).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence


def cohen_kappa(rater_a: Sequence[float], rater_b: Sequence[float]) -> float | None:
    """Cohen's κ for two raters on a categorical scale.

    Returns None when n < 2 or when both raters use a single category
    (chance agreement = 1.0 → κ undefined).
    """
    if len(rater_a) != len(rater_b):
        raise ValueError("rater_a and rater_b must be same length")
    n = len(rater_a)
    if n < 2:
        return None

    a = [round(x) for x in rater_a]
    b = [round(x) for x in rater_b]
    categories = sorted(set(a) | set(b))
    if len(categories) < 2:
        return None

    agree = sum(1 for x, y in zip(a, b, strict=True) if x == y)
    p_o = agree / n

    pa = Counter(a)
    pb = Counter(b)
    p_e = sum((pa[c] / n) * (pb[c] / n) for c in categories)
    if p_e >= 1.0:
        return None
    return (p_o - p_e) / (1.0 - p_e)


def fleiss_kappa(ratings: Sequence[Sequence[float]]) -> float | None:
    """Fleiss' κ for k raters on N items (categorical).

    `ratings[i]` is the list of category assignments for item i. Each item
    must have the same number of raters. Returns None when N < 2 or when
    only one category is used overall.
    """
    if not ratings:
        return None
    n_items = len(ratings)
    if n_items < 2:
        return None
    n_raters_per_item = len(ratings[0])
    if n_raters_per_item < 2:
        return None
    for row in ratings:
        if len(row) != n_raters_per_item:
            raise ValueError("all items must have the same number of raters")

    rounded: list[list[int]] = [[round(x) for x in row] for row in ratings]
    categories = sorted({c for row in rounded for c in row})
    if len(categories) < 2:
        return None

    counts: list[dict[int, int]] = []
    for row in rounded:
        c: dict[int, int] = dict.fromkeys(categories, 0)
        for r in row:
            c[r] += 1
        counts.append(c)

    n = n_raters_per_item
    p_j = {
        cat: sum(c[cat] for c in counts) / (n_items * n) for cat in categories
    }
    p_bar_e = sum(v * v for v in p_j.values())

    p_i_sum = 0.0
    for c in counts:
        s = sum(v * (v - 1) for v in c.values())
        p_i_sum += s / (n * (n - 1))
    p_bar_o = p_i_sum / n_items

    if p_bar_e >= 1.0:
        return None
    return (p_bar_o - p_bar_e) / (1.0 - p_bar_e)


def pearson_r(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pearson product-moment correlation. Returns None on degenerate inputs."""
    if len(xs) != len(ys):
        raise ValueError("xs and ys must be same length")
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def spearman_r(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Spearman rho via Pearson on fractional ranks (handles ties)."""
    if len(xs) != len(ys):
        raise ValueError("xs and ys must be same length")
    if len(xs) < 2:
        return None
    return pearson_r(_fractional_ranks(xs), _fractional_ranks(ys))


def _fractional_ranks(values: Sequence[float]) -> list[float]:
    """Average-rank scheme: tied values get the mean of the ranks they cover."""
    indexed = sorted(enumerate(values), key=lambda p: p[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # ranks are 1-based
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg
        i = j + 1
    return ranks
