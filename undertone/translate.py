"""Line translations via the public Google Translate web endpoint, cached per (target, text)."""
import hashlib
import json
import os
import urllib.parse

from .sources import http_json

HEADERS = {"User-Agent": "Mozilla/5.0"}


def parse_gtx(payload):
    segments = payload[0] if payload and payload[0] else []
    return "".join(seg[0] for seg in segments if seg and seg[0])


def chunk_lines(lines, budget=3500):
    chunks, cur, size = [], [], 0
    for line in lines:
        if cur and size + len(line) + 1 > budget:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        chunks.append(cur)
    return chunks


def _request(text, target, http):
    q = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": target, "dt": "t", "q": text})
    return parse_gtx(http(f"https://translate.googleapis.com/translate_a/single?{q}", HEADERS))


def _translate_chunk(lines, target, http):
    joined = _request("\n".join(lines), target, http)
    out = joined.split("\n")
    if len(out) == len(lines):
        return [o.strip() for o in out]
    return [_request(line, target, http).strip() if line.strip() else "" for line in lines]


def translate_lines(lines, target, cache_path, http=http_json):
    """Translate each line; returns a list the same length as `lines`, or None on network failure."""
    key = hashlib.sha1((target + "\n" + "\n".join(lines)).encode()).hexdigest()
    cache = {}
    try:
        with open(cache_path) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        pass
    if key in cache:
        return cache[key]
    try:
        out = []
        for chunk in chunk_lines(lines):
            non_empty = [l for l in chunk if l.strip()]
            translated = _translate_chunk(non_empty, target, http) if non_empty else []
            it = iter(translated)
            out.extend(next(it) if l.strip() else "" for l in chunk)
    except (OSError, ValueError, IndexError, TypeError, KeyError):
        return None
    cache[key] = out
    try:
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache, f)
    except OSError:
        pass
    return out
