"""Lyrics sources and the fallback chain: local .lrc files, LRCLIB, NetEase."""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from .lyrics import lrclib_search_url, lrclib_url, pick_search_result

EMPTY = {"syncedLyrics": None, "plainLyrics": None, "instrumental": False, "source": "none"}
_TS = re.compile(r"\[\d+:\d+(?:\.\d+)?\]")
_META = re.compile(r"^\[[a-zA-Z]+:[^\]]*\]\s*$")


class LyricsUnavailable(Exception):
    """Transient failure (network, 5xx) worth retrying while the track still plays."""


def http_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


# ---- local files ---------------------------------------------------------------
def _safe(name):
    return re.sub(r"[/\\\0]", "_", name).strip()


def local_lrc_candidates(track, local_dirs):
    out = []
    if track.url.startswith("file://"):
        path = urllib.parse.unquote(track.url[7:])
        out.append(os.path.splitext(path)[0] + ".lrc")
    for d in local_dirs:
        d = os.path.expanduser(d)
        if track.artist:
            out.append(os.path.join(d, f"{_safe(track.artist)} - {_safe(track.title)}.lrc"))
        out.append(os.path.join(d, f"{_safe(track.title)}.lrc"))
    return out


def plain_from_lrc(text):
    lines = []
    for raw in text.splitlines():
        if _META.match(raw):
            continue
        line = _TS.sub("", raw).strip()
        line = re.sub(r"<\d+:\d+(?:\.\d+)?>", "", line).strip()
        if line or lines:
            lines.append(line)
    return "\n".join(lines).strip()


def read_local(track, local_dirs):
    for path in local_lrc_candidates(track, local_dirs):
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            return {"syncedLyrics": text, "plainLyrics": plain_from_lrc(text), "instrumental": False, "source": "local"}
    return None


# ---- LRCLIB ----------------------------------------------------------------------
LRCLIB_HEADERS = {"User-Agent": "undertone (https://github.com/Mohit-Aasirwal/undertone)"}


def fetch_lrclib(track, http=http_json):
    duration_s = round(track.length_us / 1_000_000) if track.length_us else None
    try:
        try:
            data = http(lrclib_url(track.artist, track.title, track.album, track.length_us), LRCLIB_HEADERS)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            results = http(lrclib_search_url(track.artist, track.title), LRCLIB_HEADERS)
            data = pick_search_result(results, duration_s) if duration_s else next(
                (r for r in results if r.get("syncedLyrics") or r.get("plainLyrics")), None)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise LyricsUnavailable(f"lrclib: {e}") from e
    if not data or not (data.get("syncedLyrics") or data.get("plainLyrics") or data.get("instrumental")):
        return None
    return {"syncedLyrics": data.get("syncedLyrics"), "plainLyrics": data.get("plainLyrics"),
            "instrumental": bool(data.get("instrumental")), "source": "lrclib"}


# ---- NetEase ----------------------------------------------------------------------
NETEASE_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"}


def fetch_netease(track, http=http_json):
    q = urllib.parse.urlencode({"s": f"{track.artist} {track.title}".strip(), "type": 1, "limit": 8})
    try:
        songs = (http(f"https://music.163.com/api/search/get?{q}", NETEASE_HEADERS).get("result") or {}).get("songs") or []
        if not songs:
            return None
        want_ms = track.length_us / 1000 if track.length_us else None
        if want_ms:
            songs = sorted(songs, key=lambda s: abs((s.get("duration") or 0) - want_ms))
            if abs((songs[0].get("duration") or 0) - want_ms) > 15000:
                return None
        lyric = http(f"https://music.163.com/api/song/lyric?id={songs[0]['id']}&lv=1&tv=-1", NETEASE_HEADERS)
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        raise LyricsUnavailable(f"netease: {e}") from e
    text = ((lyric.get("lrc") or {}).get("lyric") or "").strip()
    if not text or lyric.get("nolyric") or lyric.get("uncollected"):
        return None
    synced = text if _TS.search(text) else None
    return {"syncedLyrics": synced, "plainLyrics": plain_from_lrc(text), "instrumental": False, "source": "netease"}


# ---- chain --------------------------------------------------------------------------
FETCHERS = {"lrclib": fetch_lrclib, "netease": fetch_netease}


def fetch_chain(track, sources, local_dirs, http=http_json):
    """Try each source in order; first with lyrics wins. If every source failed transiently, raise."""
    errors = []
    for name in sources:
        try:
            if name == "local":
                data = read_local(track, local_dirs)
            elif name in FETCHERS:
                data = FETCHERS[name](track, http)
            else:
                continue
        except LyricsUnavailable as e:
            errors.append(str(e))
            continue
        if data:
            return data
    if errors and len(errors) == len([s for s in sources if s in FETCHERS]):
        raise LyricsUnavailable("; ".join(errors))
    return dict(EMPTY)
