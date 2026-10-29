import unittest

from undertone.hotkeys import DEFAULT_BINDINGS, entries, merge_list, remove_ours


class HotkeyEntries(unittest.TestCase):
    def test_entries_carry_name_command_and_binding(self):
        e = entries("/usr/bin/undertone")
        keys = {x["key"] for x in e}
        self.assertIn("undertone-toggle", keys)
        toggle = next(x for x in e if x["key"] == "undertone-toggle")
        self.assertEqual(toggle["command"], "/usr/bin/undertone ctl toggle")
        self.assertEqual(toggle["binding"], DEFAULT_BINDINGS["toggle"])
        self.assertTrue(toggle["name"].startswith("Undertone"))

    def test_merge_keeps_existing_and_adds_ours_once(self):
        merged = merge_list(["custom0", "custom1"], ["undertone-toggle", "undertone-cycle-vis"])
        self.assertEqual(merged, ["custom0", "custom1", "undertone-toggle", "undertone-cycle-vis"])
        self.assertEqual(merge_list(merged, ["undertone-toggle"]), merged)

    def test_remove_ours_leaves_user_entries_alone(self):
        self.assertEqual(remove_ours(["custom0", "undertone-toggle", "custom1"]), ["custom0", "custom1"])
