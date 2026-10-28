"""Lyric timing offsets: one global value plus per-track values, persisted as JSON."""
import json
import os


def _key(track_key):
    return "|".join(str(p) for p in track_key)


class Offsets:
    def __init__(self, path):
        self.path = path
        self._global = 0
        self._tracks = {}
        try:
            with open(path) as f:
                data = json.load(f)
            self._global = int(data.get("global_ms", 0))
            self._tracks = {k: int(v) for k, v in data.get("tracks", {}).items()}
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    @property
    def global_ms(self):
        return self._global

    @global_ms.setter
    def global_ms(self, value):
        self._global = int(value)
        self._save()

    def get(self, track_key):
        return self._tracks.get(_key(track_key), 0)

    def set(self, track_key, ms):
        self._tracks[_key(track_key)] = int(ms)
        self._save()

    def nudge(self, track_key, delta_ms):
        total = self.get(track_key) + int(delta_ms)
        self.set(track_key, total)
        return total

    def total_seconds(self, track_key):
        return (self._global + self.get(track_key)) / 1000

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"global_ms": self._global, "tracks": self._tracks}, f, indent=1)
        os.replace(tmp, self.path)
