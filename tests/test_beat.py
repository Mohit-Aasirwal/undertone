import unittest

from undertone.beat import OnsetDetector


def feed_pattern(det, pattern, repeats):
    """pattern: list of energies per frame, repeated; returns frame indices where a beat fired."""
    hits = []
    i = 0
    for _ in range(repeats):
        for e in pattern:
            if det.feed(e):
                hits.append(i)
            i += 1
    return hits


class OnsetDetection(unittest.TestCase):
    FRAME_HZ = 23.4  # 48000 / 2048

    def test_silence_never_fires(self):
        det = OnsetDetector(self.FRAME_HZ)
        self.assertEqual(feed_pattern(det, [0.0], 200), [])

    def test_steady_noise_does_not_fire_repeatedly(self):
        det = OnsetDetector(self.FRAME_HZ)
        hits = feed_pattern(det, [0.5, 0.52, 0.48, 0.51], 100)
        self.assertLessEqual(len(hits), 2)  # at most the initial step

    def test_periodic_kicks_fire_once_per_kick(self):
        det = OnsetDetector(self.FRAME_HZ)
        # a kick every 12 frames (~120 bpm at 23.4 fps), decaying tail then quiet
        pattern = [1.0, 0.7, 0.4, 0.2] + [0.05] * 8
        hits = feed_pattern(det, pattern, 20)
        self.assertGreaterEqual(len(hits), 15)
        self.assertLessEqual(len(hits), 20)
        self.assertTrue(all(h % 12 == 0 for h in hits), hits)

    def test_tempo_estimate_matches_kick_period(self):
        det = OnsetDetector(self.FRAME_HZ)
        pattern = [1.0, 0.7, 0.4, 0.2] + [0.05] * 8   # 12 frames = 0.513 s = 117 bpm
        feed_pattern(det, pattern, 20)
        self.assertAlmostEqual(det.tempo_bpm(), 117, delta=4)

    def test_tempo_is_zero_without_beats(self):
        det = OnsetDetector(self.FRAME_HZ)
        feed_pattern(det, [0.0], 50)
        self.assertEqual(det.tempo_bpm(), 0)

    def test_pulse_decays_after_a_beat(self):
        det = OnsetDetector(self.FRAME_HZ)
        feed_pattern(det, [0.05] * 20, 1)
        det.feed(1.0)
        p0 = det.pulse()
        for _ in range(6):
            det.feed(0.05)
        self.assertGreater(p0, 0.9)
        self.assertLess(det.pulse(), p0 * 0.5)
