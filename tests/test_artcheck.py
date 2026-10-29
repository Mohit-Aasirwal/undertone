import os
import tempfile
import unittest

from undertone.artcheck import ArtRegistry


class GenericArt(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "art.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_same_art_for_one_artist_is_fine(self):
        reg = ArtRegistry(self.path)
        self.assertFalse(reg.note("h1", "Gojira"))
        self.assertFalse(reg.note("h1", "Gojira"))

    def test_same_art_across_two_artists_is_generic(self):
        reg = ArtRegistry(self.path)
        reg.note("h1", "Gojira")
        self.assertTrue(reg.note("h1", "TOOL"))
        self.assertTrue(reg.is_generic("h1"))

    def test_registry_persists(self):
        ArtRegistry(self.path).note("h1", "Gojira")
        reg = ArtRegistry(self.path)
        self.assertTrue(reg.note("h1", "Rammstein"))

    def test_empty_artist_does_not_count(self):
        reg = ArtRegistry(self.path)
        reg.note("h1", "")
        self.assertFalse(reg.note("h1", "Gojira"))
