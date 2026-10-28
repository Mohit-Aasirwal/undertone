import unittest

from undertone.backdrop import ken_burns_scale


class KenBurns(unittest.TestCase):
    def test_starts_at_one_and_peaks_mid_period(self):
        self.assertAlmostEqual(ken_burns_scale(0.0, period_s=40, max_scale=1.08), 1.0)
        self.assertAlmostEqual(ken_burns_scale(20.0, period_s=40, max_scale=1.08), 1.08)
        self.assertAlmostEqual(ken_burns_scale(40.0, period_s=40, max_scale=1.08), 1.0)

    def test_is_smooth_and_monotonic_on_the_way_up(self):
        vals = [ken_burns_scale(t, period_s=40, max_scale=1.08) for t in range(0, 21)]
        self.assertTrue(all(b >= a for a, b in zip(vals, vals[1:])))
        self.assertLess(vals[1] - vals[0], vals[10] - vals[9])  # eased start

    def test_disabled_motion_is_identity(self):
        self.assertEqual(ken_burns_scale(13.0, period_s=40, max_scale=1.0), 1.0)
