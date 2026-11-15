"""Unit tests for non-parametric stats."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from core.nasa_events.analysis.stats import (  # noqa: E402
    benjamini_hochberg,
    lagged_correlations,
    mann_kendall,
    pearson,
    sen_slope,
    spearman,
)


class StatsTest(unittest.TestCase):
    def test_sen_slope_linear(self):
        self.assertAlmostEqual(sen_slope([float(i) for i in range(11)]), 1.0)

    def test_mann_kendall_increasing(self):
        values = [float(i) + (i % 3) * 0.1 for i in range(40)]
        result = mann_kendall(values)
        self.assertEqual(result["trend"], "increasing")
        self.assertLess(result["p_value"], 0.05)

    def test_mann_kendall_flat(self):
        result = mann_kendall([5.0] * 20)
        self.assertEqual(result["trend"], "no trend")

    def test_pearson_perfect(self):
        result = pearson([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        self.assertAlmostEqual(result["r"], 1.0, places=6)

    def test_spearman_monotonic(self):
        result = spearman([1, 2, 3, 4, 5], [1, 4, 9, 16, 25])
        self.assertAlmostEqual(result["r"], 1.0, places=6)

    def test_lagged_correlation(self):
        x = [float((i * 7) % 13) for i in range(60)]
        y = [0.0, 0.0] + x[:-2]  # y(t) = x(t-2)
        rows = lagged_correlations(x, y, max_lag=5)
        best = max((row for row in rows if row["r"] is not None), key=lambda row: abs(row["r"]))
        self.assertEqual(best["lag"], 2)
        self.assertGreater(best["r"], 0.99)

    def test_benjamini_hochberg(self):
        qvalues = benjamini_hochberg([0.001, 0.01, 0.2, 0.5])
        self.assertTrue(all(value <= 1 for value in qvalues))
        self.assertAlmostEqual(qvalues[0], 0.004)
        self.assertLessEqual(qvalues[1], qvalues[2])


if __name__ == "__main__":
    unittest.main()
