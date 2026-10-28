"""MPRIS helpers that don't need a bus: choosing a player and shaping metadata."""
from dataclasses import dataclass


def pick_playing(statuses):
    for name, status in statuses.items():
        if status == "Playing":
            return name
    return None


@dataclass(frozen=True)
class Track:
    title: str
    artist: str
    album: str
    length_us: int
    art_url: str

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
    )
