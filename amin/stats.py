"""Statistics for comparing systems on the same eval set.

A table of percentages is not a result. With 30 items, a 10-point difference in
accuracy is indistinguishable from noise, and any "we beat X" claim built on one
is wrong. Three tools, deliberately kept to closed-form or simple resampling so
the whole repo stays on numpy:

  wilson        a confidence interval for a proportion that behaves sensibly at
                0% and 100%, where the textbook normal interval does not
  mcnemar       the correct test for two systems judged on the SAME items; it
                looks only at the items where they disagree
  bootstrap_delta
                a confidence interval for the difference between two systems,
                resampled in pairs so the pairing is preserved

Why McNemar and not a two-proportion z-test: the systems answer identical
questions, so their results are paired. Treating them as independent samples
throws away that pairing and inflates the p-value, which makes real improvements
look insignificant.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

Z_95 = 1.959963984540054


@dataclass(frozen=True)
class Interval:
    point: float
    low: float
    high: float
    n: int

    @property
    def half_width(self) -> float:
        return (self.high - self.low) / 2

    def __str__(self) -> str:
        return f"{self.point:.1%} [{self.low:.1%}, {self.high:.1%}]"

    def compact(self) -> str:
        return f"{self.point:.1%} ±{self.half_width:.1%}"


def wilson(successes: int, n: int, z: float = Z_95) -> Interval:
    """Wilson score interval for a binomial proportion.

    Preferred over the normal approximation because eval metrics live near 0 and
    1, where the normal interval produces bounds outside [0, 1] and badly wrong
    coverage. At n=0 it returns the full interval rather than dividing by zero.
    """
    if n <= 0:
        return Interval(0.0, 0.0, 1.0, 0)
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    spread = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    # Clamp to [0, 1] and to the point estimate. At p = 0 or 1 the exact bound
    # is 0 or 1, but floating point lands a hair inside (0.9999999999999999),
    # which would leave the interval technically excluding its own point
    # estimate and break any `low <= point <= high` assertion downstream.
    low = max(0.0, min(centre - spread, p))
    high = min(1.0, max(centre + spread, p))
    return Interval(p, low, high, n)


@dataclass(frozen=True)
class McNemar:
    """Result of a paired comparison on identical items.

    b: items system A passed and system B failed
    c: items system B passed and system A failed
    Items both passed or both failed carry no information about which is better
    and are excluded by construction - that is the point of the test.
    """

    b: int
    c: int
    statistic: float
    p_value: float
    n_discordant: int

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05

    def verdict(self, a_name: str = "A", b_name: str = "B") -> str:
        if self.n_discordant == 0:
            return "identical on every item"
        better = a_name if self.b > self.c else b_name
        if not self.significant:
            return (
                f"{better} ahead on {max(self.b, self.c)}/{self.n_discordant} "
                f"disagreements, p={self.p_value:.3f} - not significant"
            )
        return f"{better} better, p={self.p_value:.3f}"


def _binom_two_sided_p(b: int, n: int) -> float:
    """Exact two-sided binomial test against p=0.5 (the exact McNemar test)."""
    if n == 0:
        return 1.0
    k = min(b, n - b)
    # Sum the tail probabilities on both sides.
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def mcnemar(a_passed: list[bool], b_passed: list[bool], exact: bool | None = None) -> McNemar:
    """Paired test for whether two systems differ on the same items.

    Uses the exact binomial form when the number of disagreements is small
    (<= 25), where the chi-square approximation is unreliable; otherwise the
    continuity-corrected chi-square. Eval sets in this project are small enough
    that the exact test is usually what runs.
    """
    if len(a_passed) != len(b_passed):
        raise ValueError(f"paired test needs equal lengths, got {len(a_passed)} and {len(b_passed)}")
    b = sum(1 for x, y in zip(a_passed, b_passed, strict=True) if x and not y)
    c = sum(1 for x, y in zip(a_passed, b_passed, strict=True) if y and not x)
    n = b + c
    if exact is None:
        exact = n <= 25
    if n == 0:
        return McNemar(b, c, 0.0, 1.0, 0)
    if exact:
        return McNemar(b, c, float(min(b, c)), _binom_two_sided_p(b, n), n)
    stat = (abs(b - c) - 1) ** 2 / n
    # Survival function of chi-square with 1 df, via the error function.
    p = math.erfc(math.sqrt(stat / 2))
    return McNemar(b, c, stat, min(1.0, p), n)


def bootstrap_delta(
    a_passed: list[bool],
    b_passed: list[bool],
    iterations: int = 10_000,
    seed: int = 0,
) -> Interval:
    """Paired bootstrap CI for (rate_a - rate_b).

    Items are resampled as pairs, so the correlation between the two systems on
    easy and hard questions is preserved. An interval that straddles zero means
    the eval set cannot tell the systems apart - report that, do not round it
    away.
    """
    if len(a_passed) != len(b_passed):
        raise ValueError("paired bootstrap needs equal lengths")
    n = len(a_passed)
    if n == 0:
        return Interval(0.0, 0.0, 0.0, 0)
    a = np.asarray(a_passed, dtype=np.float64)
    b = np.asarray(b_passed, dtype=np.float64)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(iterations, n))
    deltas = a[idx].mean(axis=1) - b[idx].mean(axis=1)
    low, high = np.percentile(deltas, [2.5, 97.5])
    return Interval(float(a.mean() - b.mean()), float(low), float(high), n)


def required_n(half_width: float, p: float = 0.5, z: float = Z_95) -> int:
    """How many items are needed for a given CI half-width.

    Answers the only question that matters when designing an eval set: at p=0.5,
    the worst case, +/-10 points needs ~96 items and +/-5 points needs ~384.
    Printed by `amin bench` so the sample size is never left implicit.
    """
    if half_width <= 0:
        raise ValueError("half_width must be positive")
    return math.ceil((z * z * p * (1 - p)) / (half_width * half_width))
