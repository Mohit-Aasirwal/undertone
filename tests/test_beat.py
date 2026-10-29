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


class TempoStability(unittest.TestCase):
    FRAME_HZ = 23.4

    def test_half_time_hits_fold_into_the_main_tempo(self):
        det = OnsetDetector(self.FRAME_HZ)
        kick = [1.0, 0.7, 0.4, 0.2] + [0.05] * 8          # every 12 frames = 117 bpm
        double = kick + [1.0, 0.7, 0.4, 0.2] + [0.05] * 20  # then a 24-frame gap (58 bpm, folds to 117)
        feed_pattern(det, kick, 10)
        feed_pattern(det, double, 10)
        self.assertAlmostEqual(det.tempo_bpm(), 117, delta=3)

    def test_isolated_extra_hits_do_not_move_the_tempo(self):
        det = OnsetDetector(self.FRAME_HZ)
        kick = [1.0, 0.7, 0.4, 0.2] + [0.05] * 8
        feed_pattern(det, kick, 20)
        # one off-grid ghost hit then back to the grid
        feed_pattern(det, [1.0, 0.6, 0.05, 0.05, 0.05, 1.0, 0.7, 0.4, 0.2] + [0.05] * 3, 1)
        feed_pattern(det, kick, 20)
        self.assertAlmostEqual(det.tempo_bpm(), 117, delta=3)

    def test_tempo_window_is_long_enough_to_bridge_a_quiet_bar(self):
        det = OnsetDetector(self.FRAME_HZ)
        kick = [1.0, 0.7, 0.4, 0.2] + [0.05] * 8
        feed_pattern(det, kick, 30)
        feed_pattern(det, [0.05], 12 * 6)  # six beats of silence (~3 s)
        self.assertGreater(det.tempo_bpm(), 0)

    def test_swung_beats_report_the_underlying_tempo(self):
        # hits alternate 10 and 14 frames apart (swing): the tempo is the 12-frame average, 117 bpm
        det = OnsetDetector(self.FRAME_HZ)
        pattern = [1.0, 0.6, 0.3] + [0.05] * 7 + [1.0, 0.6, 0.3] + [0.05] * 11
        feed_pattern(det, pattern, 12)
        self.assertAlmostEqual(det.tempo_bpm(), 117, delta=3)

    def test_estimate_is_stable_across_consecutive_calls(self):
        det = OnsetDetector(self.FRAME_HZ)
        pattern = [1.0, 0.6, 0.3] + [0.05] * 7 + [1.0, 0.6, 0.3] + [0.05] * 11
        feed_pattern(det, pattern, 12)
        readings = []
        for _ in range(12):
            feed_pattern(det, pattern, 1)
            readings.append(det.tempo_bpm())
        self.assertLessEqual(max(readings) - min(readings), 4, readings)
