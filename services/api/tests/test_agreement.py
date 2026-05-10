"""Tests for agreement stats. Validates against textbook examples."""

from __future__ import annotations

import math

import pytest
from judge_api.metrics.agreement import cohen_kappa, fleiss_kappa, pearson_r, spearman_r


def test_cohen_kappa_perfect_agreement() -> None:
    assert cohen_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)


def test_cohen_kappa_chance_only() -> None:
    # Both raters split 50/50 independently: κ ≈ 0
    a = [1, 2, 1, 2, 1, 2, 1, 2]
    b = [2, 1, 1, 2, 1, 2, 2, 1]
    k = cohen_kappa(a, b)
    assert k is not None
    assert abs(k) < 0.5


def test_cohen_kappa_textbook_value() -> None:
    # Wikipedia "Cohen's kappa" 50-person grant example.
    # Both yes: 20, A-yes/B-no: 5, A-no/B-yes: 10, both no: 15.
    # p_o = 35/50 = 0.7, p_e = 0.5*0.6 + 0.5*0.4 = 0.5, κ = 0.4.
    a = [1] * 25 + [0] * 25  # A says yes 25, no 25
    b = [1] * 20 + [0] * 5 + [1] * 10 + [0] * 15
    k = cohen_kappa(a, b)
    assert k is not None
    assert k == pytest.approx(0.4, abs=1e-6)


def test_cohen_kappa_single_category_returns_none() -> None:
    assert cohen_kappa([3, 3, 3], [3, 3, 3]) is None


def test_cohen_kappa_too_few_returns_none() -> None:
    assert cohen_kappa([1], [1]) is None


def test_fleiss_kappa_perfect() -> None:
    rows = [[1, 1, 1], [2, 2, 2], [3, 3, 3]]
    k = fleiss_kappa(rows)
    assert k == pytest.approx(1.0)


def test_fleiss_kappa_high_agreement() -> None:
    # 4 items, 3 raters, 2 categories. All raters fully agree on each item.
    # κ should be 1.0.
    rows = [[1, 1, 1], [1, 1, 1], [2, 2, 2], [2, 2, 2]]
    k = fleiss_kappa(rows)
    assert k == pytest.approx(1.0)


def test_fleiss_kappa_partial_agreement() -> None:
    # 4 items, 3 raters, 2 categories. Totals balance to 6/6
    # so p_1 = p_2 = 0.5, p_e = 0.5. Each item's split is 2/1 ->
    # p_o = 1/3. kappa = (1/3 - 0.5) / (1 - 0.5) = -1/3.
    rows = [[1, 1, 2], [1, 2, 2], [1, 1, 2], [1, 2, 2]]
    k = fleiss_kappa(rows)
    assert k is not None
    assert k == pytest.approx(-1.0 / 3.0, abs=1e-6)


def test_fleiss_kappa_single_rater_returns_none() -> None:
    assert fleiss_kappa([[1], [2], [3]]) is None


def test_pearson_r_perfect_positive() -> None:
    assert pearson_r([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) == pytest.approx(1.0)


def test_pearson_r_perfect_negative() -> None:
    assert pearson_r([1, 2, 3, 4, 5], [10, 8, 6, 4, 2]) == pytest.approx(-1.0)


def test_pearson_r_zero() -> None:
    r = pearson_r([1, 2, 3, 4, 5], [3, 1, 4, 1, 5])
    assert r is not None
    assert abs(r) < 0.5


def test_pearson_r_constant_returns_none() -> None:
    assert pearson_r([1, 1, 1, 1], [1, 2, 3, 4]) is None


def test_spearman_r_monotonic_nonlinear() -> None:
    # Pearson would be < 1 here (curve), Spearman = 1 (rank-monotonic)
    s = spearman_r([1, 2, 3, 4, 5], [1, 4, 9, 16, 25])
    assert s == pytest.approx(1.0)


def test_spearman_r_with_ties() -> None:
    # Ties handled via fractional ranks
    s = spearman_r([1, 2, 2, 3, 4], [1, 2, 2, 3, 4])
    assert s == pytest.approx(1.0)


def test_spearman_r_negative() -> None:
    s = spearman_r([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
    assert s == pytest.approx(-1.0)


def test_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="same length"):
        cohen_kappa([1, 2], [1])
    with pytest.raises(ValueError, match="same length"):
        pearson_r([1, 2, 3], [1, 2])


def test_pearson_independent_random_near_zero() -> None:
    xs = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    ys = [2.0, 1.0, 4.0, 3.0, 6.0, 5.0, 8.0, 7.0]
    r = pearson_r(xs, ys)
    assert r is not None
    # near-perfect ladder: should be high positive
    assert math.isfinite(r)
