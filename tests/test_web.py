import json
import threading
import time
import unittest
import urllib.request

from undertone.web import NowPlayingServer, PAGE_HTML, snapshot_payload


class Payload(unittest.TestCase):
    def test_payload_has_the_fields_the_page_needs(self):
        st = {"track": {"title": "Silvera", "artist": "Gojira", "album": "Magma", "length_s": 206.0},
              "position_s": 12.5, "lyrics": "synced", "accent": "#e55944", "visible": True}
        p = snapshot_payload(st, lines=["a", "b"], idx=1, art_available=True, translations=None)
        self.assertEqual(p["title"], "Silvera")
        self.assertEqual(p["lines"], ["a", "b"])
        self.assertEqual(p["idx"], 1)
        self.assertEqual(p["accent"], "#e55944")
        self.assertTrue(p["art"])

    def test_payload_without_a_track_is_idle(self):
        p = snapshot_payload({"track": None, "accent": "#ffffff", "visible": False}, [], -1, False, None)
        self.assertIsNone(p["title"])
        self.assertEqual(p["lines"], [])


class Server(unittest.TestCase):
    def setUp(self):
        self.state = {"payload": {"title": "Silvera", "artist": "Gojira", "lines": ["x"], "idx": 0,
                                  "accent": "#e55944", "art": False, "position_s": 1.0, "translations": None}}
        self.srv = NowPlayingServer("127.0.0.1", 0, lambda: self.state["payload"], lambda: None, interval_s=0.05)
        self.srv.start()
        self.base = f"http://127.0.0.1:{self.srv.port}"

    def tearDown(self):
        self.srv.stop()

    def test_index_serves_the_page(self):
        body = urllib.request.urlopen(self.base + "/", timeout=3).read().decode()
        self.assertIn("<html", body.lower())
        self.assertEqual(body, PAGE_HTML)

    def test_state_endpoint_returns_json(self):
        data = json.load(urllib.request.urlopen(self.base + "/state", timeout=3))
        self.assertEqual(data["title"], "Silvera")

    def test_events_stream_sends_updates(self):
        resp = urllib.request.urlopen(self.base + "/events", timeout=3)
        first = resp.readline().decode()
        self.assertTrue(first.startswith("data: "))
        self.assertEqual(json.loads(first[6:])["title"], "Silvera")
        self.state["payload"] = {**self.state["payload"], "title": "Changed"}
        deadline = time.time() + 2
        seen = False
        while time.time() < deadline and not seen:
            line = resp.readline().decode()
            seen = line.startswith("data: ") and json.loads(line[6:])["title"] == "Changed"
        self.assertTrue(seen)

    def test_art_404_when_unavailable(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(self.base + "/art", timeout=3)
        self.assertEqual(cm.exception.code, 404)
