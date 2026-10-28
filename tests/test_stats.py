import os
import tempfile
import unittest

from undertone.player import Track
from undertone.stats import History, format_report


def track(title, artist="Gojira", album="Magma", length=200):
    return Track(title=title, artist=artist, album=album, length_us=length * 1_000_000, art_url="")


class HistoryDb(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = History(os.path.join(self.dir.name, "h.db"))

    def tearDown(self):
        self.db.close()
        self.dir.cleanup()

    def test_records_plays_and_summarises(self):
        self.db.record(track("Silvera"), played_s=200, source="lrclib", ts=1000)
        self.db.record(track("Silvera"), played_s=120, source="lrclib", ts=2000)
        self.db.record(track("Stranded", album="Magma"), played_s=270, source="local", ts=3000)
        self.db.record(track("Schism", artist="TOOL", album="Lateralus"), played_s=400, source="none", ts=4000)
        rep = self.db.report(days=None)
        self.assertEqual(rep["plays"], 4)
        self.assertEqual(rep["seconds"], 990)
        self.assertEqual(rep["top_artists"][0], ("Gojira", 3, 590))
        self.assertEqual(rep["top_tracks"][0], ("Schism", "TOOL", 1, 400))   # ranked by time listened
        self.assertEqual(rep["top_tracks"][1], ("Silvera", "Gojira", 2, 320))
        self.assertEqual(rep["lyrics_coverage"], {"lrclib": 2, "local": 1, "none": 1})

    def test_day_window_filters_old_plays(self):
        import time
        now = time.time()
        self.db.record(track("Old"), played_s=100, source="none", ts=now - 40 * 86400)
        self.db.record(track("New"), played_s=100, source="none", ts=now - 3600)
        self.assertEqual(self.db.report(days=7)["plays"], 1)
        self.assertEqual(self.db.report(days=None)["plays"], 2)

    def test_report_formats_readably(self):
        self.db.record(track("Silvera"), played_s=200, source="lrclib", ts=1000)
        text = format_report(self.db.report(days=None), days=None)
        self.assertIn("Silvera", text)
        self.assertIn("Gojira", text)
        self.assertIn("3m", text)
