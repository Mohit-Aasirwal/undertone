import colorsys
import unittest

import numpy as np

from undertone.theme import palette_from_pixels, FALLBACK_ACCENT


def hue_of(rgb):
    return colorsys.rgb_to_hsv(*rgb)[0]


class PaletteFromPixels(unittest.TestCase):
    def test_dominant_saturated_colour_becomes_accent(self):
        px = np.zeros((1000, 3))
        px[:700] = (0.8, 0.1, 0.1)   # red
        px[700:] = (0.1, 0.1, 0.9)   # blue
        accent = palette_from_pixels(px)["accent"]
        self.assertLess(min(hue_of(accent), 1 - hue_of(accent)), 0.05)  # red-ish hue near 0

    def test_grey_or_black_art_falls_back_to_neutral_accent(self):
        grey = np.full((500, 3), 0.4)
        black = np.zeros((500, 3))
        self.assertEqual(palette_from_pixels(grey)["accent"], FALLBACK_ACCENT)
        self.assertEqual(palette_from_pixels(black)["accent"], FALLBACK_ACCENT)

    def test_accent_is_bright_enough_to_read_on_dark_background(self):
        px = np.tile((0.2, 0.05, 0.3), (500, 1))  # dark purple
        accent = palette_from_pixels(px)["accent"]
        self.assertGreaterEqual(colorsys.rgb_to_hsv(*accent)[2], 0.85)

    def test_base_is_a_dark_tint_of_the_image(self):
        px = np.tile((0.9, 0.2, 0.2), (500, 1))
        base = palette_from_pixels(px)["base"]
        self.assertTrue(all(0.0 <= c <= 0.3 for c in base))
        self.assertGreater(base[0], base[1])

    def test_accepts_uint8_pixels_and_tiny_images(self):
        px = np.array([[255, 128, 0]], dtype=np.uint8)
        p = palette_from_pixels(px)
        self.assertTrue(all(0.0 <= c <= 1.0 for c in p["accent"]))
