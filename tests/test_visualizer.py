import math
import unittest

import numpy as np

from undertone.visualizer import band_levels, smooth_levels, ring_radii


class BandLevels(unittest.TestCase):
    rate, n = 48000, 2048

    def spectrum_of(self, freq):
        t = np.arange(self.n) / self.rate
        return np.abs(np.fft.rfft(np.sin(2 * math.pi * freq * t) * np.hanning(self.n)))

    def test_returns_requested_number_of_bands_in_unit_range(self):
        levels = band_levels(self.spectrum_of(440), self.rate, n_bands=8)
        self.assertEqual(len(levels), 8)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in levels))

    def test_low_tone_lands_in_lower_band_than_high_tone(self):
        low = band_levels(self.spectrum_of(80), self.rate, n_bands=8)
        high = band_levels(self.spectrum_of(8000), self.rate, n_bands=8)
        self.assertLess(int(np.argmax(low)), int(np.argmax(high)))

    def test_silence_is_all_zero(self):
        levels = band_levels(np.zeros(self.n // 2 + 1), self.rate, n_bands=8)
        self.assertTrue(all(v == 0.0 for v in levels))


class SmoothLevels(unittest.TestCase):
    def test_rises_quickly_and_falls_slowly(self):
        up = smooth_levels(np.array([0.0]), np.array([1.0]), attack=0.8, decay=0.2)
        down = smooth_levels(np.array([1.0]), np.array([0.0]), attack=0.8, decay=0.2)
        self.assertAlmostEqual(float(up[0]), 0.8)
        self.assertAlmostEqual(float(down[0]), 0.8)

    def test_unchanged_input_is_stable(self):
        out = smooth_levels(np.array([0.5]), np.array([0.5]), attack=0.8, decay=0.2)
        self.assertAlmostEqual(float(out[0]), 0.5)


class RingRadii(unittest.TestCase):
    def test_rings_are_evenly_spaced_and_grow_with_level(self):
        quiet = ring_radii(np.zeros(4), base=100, spacing=50, swell=40)
        loud = ring_radii(np.ones(4), base=100, spacing=50, swell=40)
        self.assertEqual(list(quiet), [100, 150, 200, 250])
        self.assertEqual(list(loud), [140, 190, 240, 290])


if __name__ == "__main__":
    unittest.main()
