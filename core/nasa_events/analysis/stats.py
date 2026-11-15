"""Non-parametric trend tests and correlation utilities (standard library only).

Test design:
  - Mann-Kendall S test (tie-corrected, normal approximation)
  - Sen's slope (median of pairwise slopes)
  - Pearson / Spearman correlations with Fisher-z p-values (n >= 10 recommended)
  - Lagged cross-correlations and Benjamini-Hochberg FDR correction
"""
from __future__ import annotations

import math
from collections import Counter


def _norm_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _ranks(values: list[float]) -> list[float]:
    """Average ranks for ties (1-based)."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        average = (index + end) / 2.0 + 1.0
        for position in range(index, end + 1):
            ranks[order[position]] = average
        index = end + 1
    return ranks


def sen_slope(values: list[float]) -> float | None:
    """Median of pairwise slopes (per time step). O(n^2): use monthly series."""
    n = len(values)
    if n < 2:
        return None
    slopes = [
        (values[j] - values[i]) / (j - i)
        for i in range(n - 1)
        for j in range(i + 1, n)
    ]
    slopes.sort()
    middle = len(slopes) // 2
    if len(slopes) % 2:
        return slopes[middle]
    return (slopes[middle - 1] + slopes[middle]) / 2.0


def mann_kendall(values: list[float], alpha: float = 0.05) -> dict:
    """Two-sided Mann-Kendall trend test with tie correction."""
    n = len(values)
    if n < 3:
        return {"n": n, "s": 0, "z": None, "p_value": None, "trend": "insufficient", "alpha": alpha}
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            difference = values[j] - values[i]
            s += (difference > 0) - (difference < 0)
    variance = n * (n - 1) * (2 * n + 5) / 18.0
    variance -= sum(count * (count - 1) * (2 * count + 5) for count in Counter(values).values()) / 18.0
    if variance <= 0:
        return {"n": n, "s": s, "z": None, "p_value": None, "trend": "no trend", "alpha": alpha}
    if s > 0:
        z = (s - 1) / math.sqrt(variance)
    elif s < 0:
        z = (s + 1) / math.sqrt(variance)
    else:
        z = 0.0
    p_value = 2.0 * (1.0 - _norm_cdf(abs(z)))
    if p_value < alpha:
        trend = "increasing" if s > 0 else "decreasing"
    else:
        trend = "no trend"
    return {"n": n, "s": s, "z": z, "p_value": p_value, "trend": trend, "alpha": alpha}


def pearson(x: list[float], y: list[float]) -> dict:
    n = min(len(x), len(y))
    if n < 3:
        return {"n": n, "r": None, "p": None}
    x = x[:n]
    y = y[:n]
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    covariance = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)
    if var_x == 0 or var_y == 0:
        return {"n": n, "r": None, "p": None}
    r = covariance / math.sqrt(var_x * var_y)
    r = max(-1.0, min(1.0, r))
    if n > 3 and abs(r) < 1.0:
        z = math.atanh(r) * math.sqrt(n - 3)
        p = 2.0 * (1.0 - _norm_cdf(abs(z)))
    else:
        p = 0.0 if abs(r) == 1.0 else None
    return {"n": n, "r": r, "p": p}


def spearman(x: list[float], y: list[float]) -> dict:
    n = min(len(x), len(y))
    if n < 3:
        return {"n": n, "r": None, "p": None}
    return pearson(_ranks(x[:n]), _ranks(y[:n]))


def lagged_correlations(
    x: list[float],
    y: list[float],
    max_lag: int = 6,
    method: str = "spearman",
) -> list[dict]:
    """Correlate x(t) with y(t + lag) for lag in [-max_lag, +max_lag]."""
    if method not in ("spearman", "pearson"):
        raise ValueError("method must be 'spearman' or 'pearson'")
    function = spearman if method == "spearman" else pearson
    results: list[dict] = []
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            xs = x[: len(x) - lag] if lag else list(x)
            ys = y[lag:]
        else:
            xs = x[-lag:]
            ys = y[: len(y) + lag]
        length = min(len(xs), len(ys))
        xs = xs[:length]
        ys = ys[:length]
        if length < 5:
            results.append({"lag": lag, "r": None, "p": None, "n": length})
            continue
        stats = function(xs, ys)
        results.append({"lag": lag, "r": stats["r"], "p": stats["p"], "n": stats["n"]})
    return results


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR-adjusted q-values (same order as input)."""
    count = len(pvalues)
    if not count:
        return []
    order = sorted(range(count), key=lambda index: pvalues[index])
    adjusted = [1.0] * count
    previous = 1.0
    for rank in range(count - 1, -1, -1):
        index = order[rank]
        value = min(previous, pvalues[index] * count / (rank + 1))
        adjusted[index] = value
        previous = value
    return adjusted
