import unittest
from undertone.player import pick_playing, track_from_metadata


class PickPlaying(unittest.TestCase):
    def test_returns_the_player_that_is_playing(self):
        statuses = {"org.mpris.MediaPlayer2.vlc": "Paused", "org.mpris.MediaPlayer2.brave.instance1": "Playing"}
        self.assertEqual(pick_playing(statuses), "org.mpris.MediaPlayer2.brave.instance1")

    def test_none_when_nothing_is_playing(self):
        self.assertIsNone(pick_playing({"org.mpris.MediaPlayer2.vlc": "Stopped"}))
        self.assertIsNone(pick_playing({}))


class TrackFromMetadata(unittest.TestCase):
    def test_joins_artists_and_reads_length_and_art(self):
        meta = {
            "xesam:title": "The Shooting Star",
            "xesam:artist": ["Gojira", "Someone"],
            "xesam:album": "Magma",
            "mpris:length": 342382947,
            "mpris:artUrl": "file:///tmp/art",
        }
        t = track_from_metadata(meta)
        self.assertEqual((t.title, t.artist, t.album, t.length_us, t.art_url),
                         ("The Shooting Star", "Gojira, Someone", "Magma", 342382947, "file:///tmp/art"))

    def test_missing_fields_default_to_empty(self):
        t = track_from_metadata({"xesam:title": "x"})
        self.assertEqual((t.artist, t.album, t.length_us, t.art_url), ("", "", 0, ""))

    def test_same_song_compares_equal_for_change_detection(self):
        a = track_from_metadata({"xesam:title": "x", "xesam:artist": ["y"], "mpris:length": 5})
        b = track_from_metadata({"xesam:title": "x", "xesam:artist": ["y"], "mpris:length": 5, "mpris:artUrl": "f"})
        self.assertEqual(a.key, b.key)


if __name__ == "__main__":
    unittest.main()


class PlayerFilter(unittest.TestCase):
    statuses = {"org.mpris.MediaPlayer2.brave.instance1": "Playing", "org.mpris.MediaPlayer2.spotify": "Playing"}

    def test_deny_list_skips_matching_players(self):
        self.assertEqual(pick_playing(self.statuses, deny=["brave"]), "org.mpris.MediaPlayer2.spotify")

    def test_allow_list_only_accepts_matching_players(self):
        self.assertEqual(pick_playing(self.statuses, allow=["spotify"]), "org.mpris.MediaPlayer2.spotify")
        self.assertIsNone(pick_playing(self.statuses, allow=["vlc"]))

    def test_matching_is_case_insensitive_substring(self):
        self.assertEqual(pick_playing(self.statuses, allow=["SPOT"]), "org.mpris.MediaPlayer2.spotify")

    def test_empty_lists_mean_no_filtering(self):
        self.assertEqual(pick_playing(self.statuses, allow=[], deny=[]), "org.mpris.MediaPlayer2.brave.instance1")
