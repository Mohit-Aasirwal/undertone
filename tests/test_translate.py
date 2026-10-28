import os
import tempfile
import unittest

from undertone.translate import parse_gtx, translate_lines, chunk_lines


class ParseGtx(unittest.TestCase):
    def test_joins_translated_segments(self):
        payload = [[["नमस्ते ", "Hello ", None, None], ["दुनिया", "world", None, None]], None, "en"]
        self.assertEqual(parse_gtx(payload), "नमस्ते दुनिया")

    def test_empty_payload_is_empty_string(self):
        self.assertEqual(parse_gtx([None, None, "en"]), "")


class ChunkLines(unittest.TestCase):
    def test_chunks_respect_character_budget_and_keep_order(self):
        lines = ["a" * 30, "b" * 30, "c" * 30]
        chunks = chunk_lines(lines, budget=65)
        self.assertEqual(chunks, [["a" * 30, "b" * 30], ["c" * 30]])


class TranslateLines(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cache = os.path.join(self.dir.name, "t.json")

    def tearDown(self):
        self.dir.cleanup()

    def fake_http(self, calls):
        def http(url, headers=None):
            calls.append(url)
            import urllib.parse
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
            segs = [[f"<{line}>", line, None, None] if i == 0 else [f"\n<{line}>", "\n" + line, None, None]
                    for i, line in enumerate(q.split("\n"))]
            return [segs, None, "en"]
        return http

    def test_translates_line_by_line_preserving_count(self):
        calls = []
        out = translate_lines(["one", "two", ""], "hi", self.cache, self.fake_http(calls))
        self.assertEqual(out, ["<one>", "<two>", ""])
        self.assertEqual(len(calls), 1)

    def test_second_call_is_served_from_cache(self):
        calls = []
        translate_lines(["one", "two"], "hi", self.cache, self.fake_http(calls))
        translate_lines(["one", "two"], "hi", self.cache, self.fake_http(calls))
        self.assertEqual(len(calls), 1)

    def test_network_failure_returns_none(self):
        def http(url, headers=None):
            raise OSError("offline")
        self.assertIsNone(translate_lines(["one"], "hi", self.cache, http))

    def test_count_mismatch_falls_back_to_per_line_requests(self):
        calls = []

        def http(url, headers=None):
            calls.append(url)
            import urllib.parse
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
            if "\n" in q:
                return [[["merged", q, None, None]], None, "en"]  # lost the newline
            return [[[f"<{q}>", q, None, None]], None, "en"]
        out = translate_lines(["one", "two"], "hi", self.cache, http)
        self.assertEqual(out, ["<one>", "<two>"])
