"""Spot placeholder album art: the same image handed over for different artists is a player icon."""
import json
import os


class ArtRegistry:
    def __init__(self, path):
        self.path = path
        self.seen = {}
        try:
            with open(path) as f:
                self.seen = {k: list(v) for k, v in json.load(f).items()}
        except (OSError, ValueError, AttributeError):
            pass

    def is_generic(self, art_hash):
        return len(self.seen.get(art_hash, [])) >= 2

    def note(self, art_hash, artist):
        """Record that `artist` came with this art; returns True when the art is now known to be generic."""
        if artist:
            artists = self.seen.setdefault(art_hash, [])
            if artist not in artists:
                artists.append(artist)
                self._save()
        return self.is_generic(art_hash)

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(self.seen, f)
        except OSError:
            pass
