import math
import unittest

import numpy as np

from undertone.modes import MODES, bar_layout, wave_points, ParticleField


class Modes(unittest.TestCase):
    def test_mode_list_is_stable_and_starts_with_rings(self):
        self.assertEqual(MODES, ["rings", "bars", "wave", "particles"])


class BarLayout(unittest.TestCase):
    def test_bars_are_mirrored_around_the_circle_with_lengths_from_levels(self):
        levels = np.array([1.0, 0.5, 0.0])
        bars = bar_layout(levels, inner_r=100, max_len=50)
        self.assertEqual(len(bars), 6)  # each band mirrored left/right
        angles = sorted(round(b[0], 3) for b in bars)
        self.assertEqual(len(set(angles)), 6)
        lengths = {round(b[1]) for b in bars}
        self.assertEqual(lengths, {100 + 50, 100 + 25, 100 + 0})

    def test_bars_span_the_full_circle(self):
        bars = bar_layout(np.ones(8), inner_r=10, max_len=5)
        angles = [b[0] for b in bars]
        self.assertGreater(max(angles) - min(angles), 1.5 * math.pi)


class WavePoints(unittest.TestCase):
    def test_wave_radius_oscillates_around_base_scaled_by_levels(self):
        pts = wave_points(np.full(4, 0.5), base_r=100, amp=20, phase=0.0, n_points=64)
        self.assertEqual(len(pts), 64)
        radii = [math.hypot(x, y) for x, y in pts]
        self.assertGreaterEqual(min(radii), 100 - 20 * 0.5 - 1e-6)
        self.assertLessEqual(max(radii), 100 + 20 * 0.5 + 1e-6)

    def test_silence_is_a_perfect_circle(self):
        pts = wave_points(np.zeros(4), base_r=100, amp=20, phase=1.0, n_points=32)
        self.assertTrue(all(abs(math.hypot(x, y) - 100) < 1e-6 for x, y in pts))


class Particles(unittest.TestCase):
    def test_beat_emits_particles_and_they_move_outward_then_die(self):
        field = ParticleField(max_particles=200, seed=1)
        field.step(dt=0.033, pulse=0.0, level=0.2, beat=False)
        self.assertEqual(len(field.particles), 0)
        field.step(dt=0.033, pulse=1.0, level=0.8, beat=True)
        n = len(field.particles)
        self.assertGreater(n, 0)
        r0 = [p.r for p in field.particles]
        field.step(dt=0.033, pulse=0.5, level=0.8, beat=False)
        self.assertTrue(all(b > a for a, b in zip(r0, [p.r for p in field.particles])))
        for _ in range(400):
            field.step(dt=0.033, pulse=0.0, level=0.0, beat=False)
        self.assertEqual(len(field.particles), 0)

    def test_never_exceeds_max_particles(self):
        field = ParticleField(max_particles=30, seed=1)
        for _ in range(50):
            field.step(dt=0.033, pulse=1.0, level=1.0, beat=True)
        self.assertLessEqual(len(field.particles), 30)
