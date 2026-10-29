"""MPRIS helpers that don't need a bus: choosing a player and shaping metadata."""
from dataclasses import dataclass


MPRIS_PREFIX = "org.mpris.MediaPlayer2."


def player_allowed(name, allow=None, deny=None):
    """Case-insensitive substring match on the bus name after the MPRIS prefix."""
    short = name[len(MPRIS_PREFIX):].lower() if name.startswith(MPRIS_PREFIX) else name.lower()
    if deny and any(d.lower() in short for d in deny):
        return False
    if allow and not any(a.lower() in short for a in allow):
        return False
    return True


def pick_playing(statuses, allow=None, deny=None):
    for name, status in statuses.items():
        if status == "Playing" and player_allowed(name, allow, deny):
            return name
    return None


@dataclass(frozen=True)
class Track:
    title: str
    artist: str
    album: str
    length_us: int
    art_url: str
    url: str = ""

    @property
    def key(self):
        return (self.title, self.artist, self.album, self.length_us)


def track_from_metadata(meta):
    artists = meta.get("xesam:artist") or []
    if isinstance(artists, str):
        artists = [artists]
    return Track(
        title=meta.get("xesam:title") or "",
        artist=", ".join(artists),
        album=meta.get("xesam:album") or "",
        length_us=int(meta.get("mpris:length") or 0),
        art_url=meta.get("mpris:artUrl") or "",
        url=meta.get("xesam:url") or "",
    )


DEFAULT_PROFILE = {"offset_ms": 0, "art": True}


def profile_for(name, profiles):
    """Per-player settings: the first profile whose key is a substring of the player's bus name."""
    short = name[len(MPRIS_PREFIX):].lower() if name.startswith(MPRIS_PREFIX) else name.lower()
    merged = dict(DEFAULT_PROFILE)
    for key, values in (profiles or {}).items():
        if key.lower() in short and isinstance(values, dict):
            merged.update(values)
            break
    return merged
