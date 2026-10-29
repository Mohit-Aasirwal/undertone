import unittest

from undertone.player import profile_for


class Profiles(unittest.TestCase):
    profiles = {"spotify": {"offset_ms": -80, "art": True}, "brave": {"art": False}}

    def test_matches_player_by_substring_of_bus_name(self):
        p = profile_for("org.mpris.MediaPlayer2.brave.instance4426", self.profiles)
        self.assertEqual(p["art"], False)
        self.assertEqual(p["offset_ms"], 0)

    def test_unknown_player_gets_defaults(self):
        p = profile_for("org.mpris.MediaPlayer2.vlc", self.profiles)
        self.assertEqual((p["offset_ms"], p["art"]), (0, True))

    def test_no_profiles_at_all(self):
        p = profile_for("org.mpris.MediaPlayer2.vlc", None)
        self.assertEqual(p["offset_ms"], 0)
