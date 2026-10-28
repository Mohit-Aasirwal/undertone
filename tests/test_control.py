import unittest

from undertone.control import parse_ctl


class ParseCtl(unittest.TestCase):
    def test_simple_commands_map_to_methods(self):
        self.assertEqual(parse_ctl(["toggle"]), ("Toggle", []))
        self.assertEqual(parse_ctl(["show"]), ("Show", []))
        self.assertEqual(parse_ctl(["hide"]), ("Hide", []))
        self.assertEqual(parse_ctl(["cycle-vis"]), ("CycleVisualizer", []))
        self.assertEqual(parse_ctl(["status"]), ("Status", []))

    def test_nudge_and_offsets_take_milliseconds(self):
        self.assertEqual(parse_ctl(["nudge", "+300"]), ("Nudge", [300]))
        self.assertEqual(parse_ctl(["nudge", "-50"]), ("Nudge", [-50]))
        self.assertEqual(parse_ctl(["offset", "120"]), ("SetOffset", [120]))
        self.assertEqual(parse_ctl(["global-offset", "-200"]), ("SetGlobalOffset", [-200]))

    def test_unknown_or_malformed_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse_ctl(["dance"])
        with self.assertRaises(ValueError):
            parse_ctl(["nudge"])
        with self.assertRaises(ValueError):
            parse_ctl(["nudge", "lots"])
