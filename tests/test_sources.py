import os
import tempfile
import unittest
import urllib.error

from undertone.player import Track
from undertone.sources import (LyricsUnavailable, fetch_chain, fetch_lrclib, fetch_netease,
                               local_lrc_candidates, read_local)

TRACK = Track(title="Silvera", artist="Gojira", album="Magma", length_us=206_000_000, art_url="")
LRC = "[00:01.00] first\n[00:05.00] second\n"


def http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, None)


class LocalFiles(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def test_candidates_include_sidecar_of_file_url_and_artist_title_in_dirs(self):
        t = Track(title="Silvera", artist="Gojira", album="", length_us=0, art_url="",
                  url="file:///music/Gojira/Silvera.mp3")
        c = local_lrc_candidates(t, ["/lyrics"])
        self.assertEqual(c[0], "/music/Gojira/Silvera.lrc")
        self.assertIn("/lyrics/Gojira - Silvera.lrc", c)
        self.assertIn("/lyrics/Silvera.lrc", c)

    def test_reads_first_existing_candidate(self):
        with open(os.path.join(self.dir.name, "Gojira - Silvera.lrc"), "w") as f:
            f.write(LRC)
        data = read_local(TRACK, [self.dir.name])
        self.assertEqual(data["syncedLyrics"], LRC)
        self.assertEqual(data["plainLyrics"], "first\nsecond")
        self.assertEqual(data["source"], "local")

    def test_missing_returns_none(self):
        self.assertIsNone(read_local(TRACK, [self.dir.name]))

    def test_slashes_in_titles_are_sanitised(self):
        t = Track(title="AC/DC Live", artist="Band", album="", length_us=0, art_url="")
        self.assertTrue(all("AC/DC" not in c for c in local_lrc_candidates(t, ["/l"])))


class Lrclib(unittest.TestCase):
    def test_exact_hit(self):
        calls = []

        def http(url, headers=None):
            calls.append(url)
            return {"syncedLyrics": LRC, "plainLyrics": "first\nsecond", "instrumental": False}
        data = fetch_lrclib(TRACK, http)
        self.assertEqual(data["syncedLyrics"], LRC)
        self.assertEqual(data["source"], "lrclib")
        self.assertIn("duration=206", calls[0])

    def test_404_falls_back_to_search(self):
        def http(url, headers=None):
            if "/api/get" in url:
                raise http_error(404)
            return [{"syncedLyrics": LRC, "plainLyrics": "p", "duration": 207}]
        self.assertEqual(fetch_lrclib(TRACK, http)["syncedLyrics"], LRC)

    def test_partial_metadata_still_queries(self):
        t = Track(title="Silvera", artist="Gojira", album="", length_us=0, art_url="")
        seen = []

        def http(url, headers=None):
            seen.append(url)
            if "/api/get" in url:
                raise http_error(404)
            return [{"syncedLyrics": LRC, "plainLyrics": "p", "duration": 206}]
        self.assertEqual(fetch_lrclib(t, http)["syncedLyrics"], LRC)
        self.assertNotIn("album_name", seen[0])
        self.assertNotIn("duration", seen[0])

    def test_server_error_raises_unavailable(self):
        def http(url, headers=None):
            raise http_error(503)
        with self.assertRaises(LyricsUnavailable):
            fetch_lrclib(TRACK, http)


class Netease(unittest.TestCase):
    def test_picks_closest_duration_and_returns_lrc(self):
        def http(url, headers=None):
            if "search" in url:
                return {"result": {"songs": [{"id": 1, "duration": 150000}, {"id": 2, "duration": 206500}]}}
            self.assertIn("id=2", url)
            return {"lrc": {"lyric": "[by:someone]\n" + LRC}}
        data = fetch_netease(TRACK, http)
        self.assertIn("[00:01.00] first", data["syncedLyrics"])
        self.assertEqual(data["source"], "netease")

    def test_no_lyric_returns_none(self):
        def http(url, headers=None):
            if "search" in url:
                return {"result": {"songs": [{"id": 1, "duration": 206000}]}}
            return {"nolyric": True}
        self.assertIsNone(fetch_netease(TRACK, http))

    def test_no_results_returns_none(self):
        self.assertIsNone(fetch_netease(TRACK, lambda url, headers=None: {"result": {}}))


class Chain(unittest.TestCase):
    def test_first_source_with_lyrics_wins_in_configured_order(self):
        def http(url, headers=None):
            if "lrclib" in url:
                return {"syncedLyrics": LRC, "plainLyrics": "p"}
            raise AssertionError("netease should not be queried")
        data = fetch_chain(TRACK, ["local", "lrclib", "netease"], [], http)
        self.assertEqual(data["source"], "lrclib")

    def test_failing_source_is_skipped_and_chain_continues(self):
        def http(url, headers=None):
            if "lrclib" in url:
                raise http_error(503)
            if "search" in url:
                return {"result": {"songs": [{"id": 9, "duration": 206000}]}}
            return {"lrc": {"lyric": LRC}}
        self.assertEqual(fetch_chain(TRACK, ["lrclib", "netease"], [], http)["source"], "netease")

    def test_all_sources_failing_raises_unavailable(self):
        def http(url, headers=None):
            raise urllib.error.URLError("offline")
        with self.assertRaises(LyricsUnavailable):
            fetch_chain(TRACK, ["lrclib", "netease"], [], http)

    def test_all_sources_empty_gives_a_none_result(self):
        def http(url, headers=None):
            if "/api/get" in url:
                raise http_error(404)
            return [] if "lrclib" in url else {"result": {}}
        data = fetch_chain(TRACK, ["lrclib", "netease"], [], http)
        self.assertIsNone(data["syncedLyrics"])
        self.assertEqual(data["source"], "none")
