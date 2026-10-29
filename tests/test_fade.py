import unittest

from undertone.fade import Fader


class FaderCurve(unittest.TestCase):
    def test_fade_in_rises_from_zero_to_one_over_the_duration(self):
        f = Fader(duration_s=0.3)
        f.start(target=1.0, now=10.0)
        self.assertAlmostEqual(f.value(10.0), 0.0)
        self.assertAlmostEqual(f.value(10.15), 0.5, places=2)
        self.assertAlmostEqual(f.value(10.3), 1.0)
        self.assertFalse(f.active(10.31))

    def test_fade_out_starts_from_the_current_value(self):
        f = Fader(duration_s=0.3)
        f.start(target=1.0, now=0.0)
        f.start(target=0.0, now=0.15)        # reverse midway: from 0.5 down to 0
        self.assertAlmostEqual(f.value(0.15), 0.5, places=2)
        self.assertAlmostEqual(f.value(0.45), 0.0)

    def test_idle_fader_holds_its_target(self):
        f = Fader(duration_s=0.3)
        self.assertEqual(f.value(5.0), 1.0)
        self.assertFalse(f.active(5.0))
