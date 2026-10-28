import os
import tempfile
import unittest

from undertone.offsets import Offsets


class OffsetsStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "offsets.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_defaults_to_zero(self):
        o = Offsets(self.path)
        self.assertEqual(o.global_ms, 0)
        self.assertEqual(o.get(("t", "a", "al", 1)), 0)

    def test_per_track_offset_persists_across_instances(self):
        Offsets(self.path).set(("t", "a", "al", 1), 250)
        self.assertEqual(Offsets(self.path).get(("t", "a", "al", 1)), 250)

    def test_global_offset_persists(self):
        o = Offsets(self.path)
        o.global_ms = -120
        self.assertEqual(Offsets(self.path).global_ms, -120)

    def test_nudge_adds_to_track_offset_and_returns_total(self):
        o = Offsets(self.path)
        self.assertEqual(o.nudge(("t", "a", "al", 1), 100), 100)
        self.assertEqual(o.nudge(("t", "a", "al", 1), -40), 60)

    def test_total_seconds_combines_global_and_track(self):
        o = Offsets(self.path)
        o.global_ms = 100
        o.set(("t", "a", "al", 1), 250)
        self.assertAlmostEqual(o.total_seconds(("t", "a", "al", 1)), 0.35)

    def test_corrupt_file_is_ignored(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(Offsets(self.path).global_ms, 0)
