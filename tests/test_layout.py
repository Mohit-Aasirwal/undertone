import unittest
from undertone.layout import select_monitors, resolve_box, window_config_for, DEFAULT_WINDOW

MONS = [{"index": 0, "name": "HDMI-A-0", "primary": True}, {"index": 1, "name": "DP-1-0", "primary": False}]
GEOM = (1920, 0, 1920, 1080)


class SelectMonitors(unittest.TestCase):
    def test_all(self):
        self.assertEqual([m["index"] for m in select_monitors(MONS, "all")], [0, 1])

    def test_primary(self):
        self.assertEqual([m["index"] for m in select_monitors(MONS, "primary")], [0])

    def test_by_name_or_index_list(self):
        self.assertEqual([m["index"] for m in select_monitors(MONS, ["DP-1-0", 0])], [1, 0])

    def test_unknown_entries_are_ignored(self):
        self.assertEqual(select_monitors(MONS, ["nope", 7]), [])


class ResolveBox(unittest.TestCase):
    def test_fill_is_whole_monitor(self):
        self.assertEqual(resolve_box(GEOM, width="fill", height="fill", ratio=None, anchor="center", margin=0), GEOM)

    def test_pixel_width_with_ratio_centered(self):
        self.assertEqual(resolve_box(GEOM, width=1280, height=None, ratio="16:9", anchor="center", margin=0),
                         (1920 + 320, 180, 1280, 720))

    def test_percent_width_with_ratio(self):
        x, y, w, h = resolve_box(GEOM, width="50%", height=None, ratio="4:3", anchor="center", margin=0)
        self.assertEqual((w, h), (960, 720))

    def test_fill_width_with_ratio_limits_height(self):
        x, y, w, h = resolve_box(GEOM, width="fill", height=None, ratio="21:9", anchor="top", margin=0)
        self.assertEqual((x, y, w, h), (1920, 0, 1920, 823))

    def test_ratio_taller_than_monitor_shrinks_to_fit(self):
        x, y, w, h = resolve_box(GEOM, width="fill", height=None, ratio="1:1", anchor="center", margin=0)
        self.assertEqual((w, h), (1080, 1080))
        self.assertEqual(x, 1920 + 420)

    def test_explicit_width_and_height_ignore_ratio(self):
        x, y, w, h = resolve_box(GEOM, width=800, height=300, ratio="16:9", anchor="center", margin=0)
        self.assertEqual((w, h), (800, 300))

    def test_anchor_bottom_right_with_margin(self):
        self.assertEqual(resolve_box(GEOM, width=400, height=200, ratio=None, anchor="bottom-right", margin=40),
                         (1920 + 1920 - 400 - 40, 1080 - 200 - 40, 400, 200))

    def test_anchor_left_is_vertically_centered(self):
        self.assertEqual(resolve_box(GEOM, width=400, height=200, ratio=None, anchor="left", margin=10),
                         (1930, 440, 400, 200))


class WindowConfigFor(unittest.TestCase):
    def test_defaults_when_nothing_configured(self):
        self.assertEqual(window_config_for({}, MONS[0]), DEFAULT_WINDOW)

    def test_global_window_section_overrides_defaults(self):
        cfg = {"window": {"width": "70%", "ratio": "16:9"}}
        c = window_config_for(cfg, MONS[0])
        self.assertEqual((c["width"], c["ratio"], c["anchor"]), ("70%", "16:9", DEFAULT_WINDOW["anchor"]))

    def test_per_monitor_override_by_name_beats_global(self):
        cfg = {"window": {"width": "70%", "DP-1-0": {"width": 640, "anchor": "bottom-left"}}}
        self.assertEqual(window_config_for(cfg, MONS[1])["width"], 640)
        self.assertEqual(window_config_for(cfg, MONS[0])["width"], "70%")

    def test_per_monitor_override_by_index(self):
        cfg = {"window": {"0": {"scale": 0.5}}}
        self.assertEqual(window_config_for(cfg, MONS[0])["scale"], 0.5)
        self.assertEqual(window_config_for(cfg, MONS[1])["scale"], DEFAULT_WINDOW["scale"])


if __name__ == "__main__":
    unittest.main()
