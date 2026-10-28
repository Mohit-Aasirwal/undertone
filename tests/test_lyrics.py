import unittest
from undertone.lyrics import parse_lrc, current_line_index, lyrics_from_response, lrclib_url


class ParseLrc(unittest.TestCase):
    def test_parses_timestamped_lines_in_time_order(self):
        text = "[00:12.50] second\n[00:01.00] first\n"
        self.assertEqual(parse_lrc(text), [(1.0, "first"), (12.5, "second")])

    def test_skips_metadata_tags_and_blank_lines(self):
        text = "[ar:Gojira]\n[ti:Song]\n\n[00:05.00] hello\n"
        self.assertEqual(parse_lrc(text), [(5.0, "hello")])

    def test_expands_multiple_timestamps_on_one_line(self):
        text = "[00:02.00][00:08.00] chorus\n"
        self.assertEqual(parse_lrc(text), [(2.0, "chorus"), (8.0, "chorus")])

    def test_keeps_empty_lyric_lines_as_instrumental_gaps(self):
        text = "[00:01.00] a\n[00:03.00]\n"
        self.assertEqual(parse_lrc(text), [(1.0, "a"), (3.0, "")])


class CurrentLineIndex(unittest.TestCase):
    lines = [(1.0, "a"), (5.0, "b"), (9.0, "c")]

    def test_before_first_line_is_minus_one(self):
        self.assertEqual(current_line_index(self.lines, 0.5), -1)

    def test_returns_last_line_at_or_before_position(self):
        self.assertEqual(current_line_index(self.lines, 5.0), 1)
        self.assertEqual(current_line_index(self.lines, 7.9), 1)

    def test_past_last_line_stays_on_last(self):
        self.assertEqual(current_line_index(self.lines, 100.0), 2)


class LyricsFromResponse(unittest.TestCase):
    def test_prefers_synced_lyrics(self):
        res = lyrics_from_response({"syncedLyrics": "[00:01.00] a", "plainLyrics": "a"})
        self.assertEqual(res.synced, [(1.0, "a")])
        self.assertEqual(res.plain, "a")

    def test_falls_back_to_plain_when_no_synced(self):
        res = lyrics_from_response({"syncedLyrics": None, "plainLyrics": "la\nla"})
        self.assertIsNone(res.synced)
        self.assertEqual(res.plain, "la\nla")

    def test_instrumental_track_has_neither(self):
        res = lyrics_from_response({"instrumental": True, "syncedLyrics": None, "plainLyrics": None})
        self.assertIsNone(res.synced)
        self.assertIsNone(res.plain)
        self.assertTrue(res.instrumental)


class LrclibUrl(unittest.TestCase):
    def test_encodes_track_fields_and_duration_in_seconds(self):
        url = lrclib_url(artist="Gojira", title="The Shooting Star", album="Magma", duration_us=342382947)
        self.assertTrue(url.startswith("https://lrclib.net/api/get?"))
        self.assertIn("artist_name=Gojira", url)
        self.assertIn("track_name=The+Shooting+Star", url)
        self.assertIn("album_name=Magma", url)
        self.assertIn("duration=342", url)


if __name__ == "__main__":
    unittest.main()


from undertone.lyrics import pick_search_result, lrclib_search_url  # noqa: E402


class PickSearchResult(unittest.TestCase):
    def test_prefers_result_with_synced_lyrics_closest_in_duration(self):
        results = [
            {"syncedLyrics": None, "plainLyrics": "p", "duration": 342},
            {"syncedLyrics": "[00:01.00] far", "plainLyrics": "x", "duration": 400},
            {"syncedLyrics": "[00:01.00] near", "plainLyrics": "x", "duration": 345},
        ]
        self.assertEqual(pick_search_result(results, duration_s=342)["syncedLyrics"], "[00:01.00] near")

    def test_falls_back_to_plain_only_result(self):
        results = [{"syncedLyrics": None, "plainLyrics": "p", "duration": 340}]
        self.assertEqual(pick_search_result(results, duration_s=342)["plainLyrics"], "p")

    def test_rejects_results_too_far_in_duration(self):
        results = [{"syncedLyrics": "[00:01.00] a", "plainLyrics": "a", "duration": 500}]
        self.assertIsNone(pick_search_result(results, duration_s=342))

    def test_none_for_empty(self):
        self.assertIsNone(pick_search_result([], duration_s=1))


class LrclibSearchUrl(unittest.TestCase):
    def test_builds_search_by_track_and_artist(self):
        url = lrclib_search_url(artist="Gojira", title="Silvera")
        self.assertTrue(url.startswith("https://lrclib.net/api/search?"))
        self.assertIn("track_name=Silvera", url)
        self.assertIn("artist_name=Gojira", url)


from undertone.lyrics import parse_enhanced_lrc, word_progress  # noqa: E402


class ParseEnhancedLrc(unittest.TestCase):
    def test_plain_synced_lines_have_no_words(self):
        self.assertEqual(parse_enhanced_lrc("[00:01.00] hello world\n"), [(1.0, "hello world", None)])

    def test_word_timestamps_are_extracted_with_clean_text(self):
        text = "[00:10.00] <00:10.00> Hello <00:10.50> big <00:11.20> world\n"
        self.assertEqual(parse_enhanced_lrc(text),
                         [(10.0, "Hello big world", [(10.0, "Hello"), (10.5, "big"), (11.2, "world")])])

    def test_mixed_files_keep_order_and_skip_metadata(self):
        text = "[ti:x]\n[00:05.00] <00:05.00> a <00:05.50> b\n[00:02.00] plain\n"
        parsed = parse_enhanced_lrc(text)
        self.assertEqual([p[0] for p in parsed], [2.0, 5.0])
        self.assertIsNone(parsed[0][2])
        self.assertEqual(parsed[1][1], "a b")


class WordProgress(unittest.TestCase):
    words = [(10.0, "Hello"), (10.5, "big"), (11.2, "world")]

    def test_before_first_word_is_zero_and_after_last_is_one(self):
        self.assertEqual(word_progress(self.words, 9.0, line_end=12.0), 0.0)
        self.assertEqual(word_progress(self.words, 12.5, line_end=12.0), 1.0)

    def test_progress_is_character_weighted_and_interpolates_within_a_word(self):
        total = len("Hello big world")
        # at 10.5 exactly "Hello " is done: 6 of 15 characters
        self.assertAlmostEqual(word_progress(self.words, 10.5, line_end=12.0), 6 / total, places=3)
        # halfway through "big" (10.5..11.2) adds half of "big " (4 chars)
        self.assertAlmostEqual(word_progress(self.words, 10.85, line_end=12.0), (6 + 2) / total, places=3)

    def test_no_words_means_fully_sung(self):
        self.assertEqual(word_progress(None, 10.0, line_end=12.0), 1.0)
