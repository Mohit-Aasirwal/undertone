"""Pure lyrics logic: LRC parsing, line lookup, LRCLIB request/response handling."""
import re
from dataclasses import dataclass
from urllib.parse import urlencode

_TS = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


def parse_lrc(text):
    out = []
    for raw in text.splitlines():
        stamps = _TS.findall(raw)
        if not stamps:
            continue
        lyric = _TS.sub("", raw).strip()
        for m, s in stamps:
            out.append((int(m) * 60 + float(s), lyric))
    out.sort(key=lambda t: t[0])
    return out


def current_line_index(lines, position):
    idx = -1
    for i, (t, _) in enumerate(lines):
        if t <= position:
            idx = i
        else:
            break
    return idx


@dataclass
class Lyrics:
    synced: list | None
    plain: str | None
    instrumental: bool = False


def lyrics_from_response(data):
    synced_text = data.get("syncedLyrics")
    return Lyrics(
        synced=parse_lrc(synced_text) if synced_text else None,
        plain=data.get("plainLyrics") or None,
        instrumental=bool(data.get("instrumental")),
    )


def lrclib_url(artist, title, album, duration_us):
    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration_us:
        params["duration"] = int(round(duration_us / 1_000_000))
    return "https://lrclib.net/api/get?" + urlencode(params)


def lrclib_search_url(artist, title):
    return "https://lrclib.net/api/search?" + urlencode({"track_name": title, "artist_name": artist})


def pick_search_result(results, duration_s, tolerance_s=15):
    """Best LRCLIB search hit: synced beats plain, then closest duration, within tolerance."""
    candidates = [r for r in results if abs((r.get("duration") or 0) - duration_s) <= tolerance_s
                  and (r.get("syncedLyrics") or r.get("plainLyrics"))]
    if not candidates:
        return None
    return min(candidates, key=lambda r: (0 if r.get("syncedLyrics") else 1,
                                          abs((r.get("duration") or 0) - duration_s)))
