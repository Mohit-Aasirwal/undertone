import unittest

from undertone.wayland import layer_margins, wants_layer_shell


class WantsLayerShell(unittest.TestCase):
    def test_only_on_wayland_with_bindings(self):
        self.assertTrue(wants_layer_shell("wayland", available=True))
        self.assertFalse(wants_layer_shell("wayland", available=False))
        self.assertFalse(wants_layer_shell("x11", available=True))


class LayerMargins(unittest.TestCase):
    def test_box_offsets_are_relative_to_the_monitor_origin(self):
        self.assertEqual(layer_margins(box=(1920 + 320, 180, 1280, 720), monitor=(1920, 0, 1920, 1080)), (320, 180))

    def test_full_monitor_box_has_zero_margins(self):
        self.assertEqual(layer_margins(box=(0, 0, 1920, 1080), monitor=(0, 0, 1920, 1080)), (0, 0))
