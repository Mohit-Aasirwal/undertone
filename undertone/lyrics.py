"""Pure lyrics logic: LRC parsing, line lookup, LRCLIB request/response handling."""
import re
from dataclasses import dataclass
from urllib.parse import urlencode

_TS = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
_WORD_TS = re.compile(r"<(\d+):(\d+(?:\.\d+)?)>")


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


def parse_enhanced_lrc(text):
    """Like parse_lrc but keeps per-word timing from <mm:ss.xx> tags.

    Returns [(line_time, clean_text, words_or_None)] where words is [(time, word), ...]."""
    out = []
    for raw in text.splitlines():
        stamps = _TS.findall(raw)
        if not stamps:
            continue
        body = _TS.sub("", raw).strip()
        words = None
        if _WORD_TS.search(body):
            words = []
            parts = _WORD_TS.split(body)  # [lead, m, s, text, m, s, text, ...]
            for i in range(1, len(parts), 3):
                t = int(parts[i]) * 60 + float(parts[i + 1])
                word = parts[i + 2].strip()
                if word:
                    words.append((t, word))
            body = " ".join(w for _, w in words)
        for m, sec in stamps:
            out.append((int(m) * 60 + float(sec), body, words))
    out.sort(key=lambda t: t[0])
    return out


def word_progress(words, position, line_end):
    """Fraction (0..1) of the line's characters sung by `position`, interpolating inside the current word."""
    if not words:
        return 1.0
    total = sum(len(w) for _, w in words) + (len(words) - 1)  # words plus single spaces
    if total <= 0:
        return 1.0
    done = 0.0
    for i, (t, w) in enumerate(words):
        length = len(w) + (1 if i < len(words) - 1 else 0)
        nxt = words[i + 1][0] if i + 1 < len(words) else max(line_end, t + 0.01)
        if position >= nxt:
            done += length
        elif position > t:
            done += length * (position - t) / max(nxt - t, 1e-6)
            break
        else:
            break
    return max(0.0, min(1.0, done / total))


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
    synced: list | None            # [(time, text)]
    plain: str | None
    instrumental: bool = False
    source: str = "none"
    words: list | None = None      # parallel to synced: [(time, word)] per line, or None


def lyrics_from_response(data):
    synced_text = data.get("syncedLyrics")
    enhanced = parse_enhanced_lrc(synced_text) if synced_text else []
    return Lyrics(
        synced=[(t, text) for t, text, _ in enhanced] if enhanced else None,
        words=[w for _, _, w in enhanced] if enhanced else None,
        plain=data.get("plainLyrics") or None,
        instrumental=bool(data.get("instrumental")),
        source=data.get("source") or "none",
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
