"""Listening history in SQLite and the `undertone stats` report."""
import os
import sqlite3
import time

DB_PATH = os.path.expanduser("~/.local/share/undertone/history.db")
MIN_PLAY_S = 30  # a play shorter than this is a skip, not a listen


class History:
    def __init__(self, path=DB_PATH):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS plays (
            ts REAL NOT NULL, title TEXT, artist TEXT, album TEXT,
            length_s REAL, played_s REAL, source TEXT)""")
        self.conn.commit()

    def record(self, track, played_s, source, ts=None):
        self.conn.execute("INSERT INTO plays VALUES (?,?,?,?,?,?,?)",
                          (ts or time.time(), track.title, track.artist, track.album,
                           track.length_us / 1_000_000, played_s, source))
        self.conn.commit()

    def report(self, days=7, limit=10):
        since = time.time() - days * 86400 if days else 0
        q = lambda sql, *a: self.conn.execute(sql, (since, *a)).fetchall()  # noqa: E731
        plays, seconds = q("SELECT COUNT(*), COALESCE(SUM(played_s),0) FROM plays WHERE ts >= ?")[0]
        return {
            "plays": plays, "seconds": int(seconds),
            "top_artists": q("SELECT artist, COUNT(*), CAST(SUM(played_s) AS INT) FROM plays WHERE ts >= ? "
                             "GROUP BY artist ORDER BY SUM(played_s) DESC LIMIT ?", limit),
            "top_tracks": q("SELECT title, artist, COUNT(*), CAST(SUM(played_s) AS INT) FROM plays WHERE ts >= ? "
                            "GROUP BY title, artist ORDER BY SUM(played_s) DESC LIMIT ?", limit),
            "lyrics_coverage": dict(q("SELECT source, COUNT(*) FROM plays WHERE ts >= ? GROUP BY source")),
        }

    def close(self):
        self.conn.close()


def _dur(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    h, m = divmod(int(seconds) // 60, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def format_report(rep, days=7):
    span = f"last {days} days" if days else "all time"
    lines = [f"Undertone listening stats ({span})", f"  {rep['plays']} plays, {_dur(rep['seconds'])} listened", ""]
    lines.append("Top artists")
    for artist, n, secs in rep["top_artists"]:
        lines.append(f"  {_dur(secs):>8}  {artist}  ({n} plays)")
    lines += ["", "Top tracks"]
    for title, artist, n, secs in rep["top_tracks"]:
        lines.append(f"  {_dur(secs):>8}  {title} — {artist}  ({n} plays)")
    cov = rep["lyrics_coverage"]
    if cov:
        total = sum(cov.values())
        found = sum(v for k, v in cov.items() if k not in ("none", None))
        lines += ["", f"Lyrics found for {found} of {total} plays  " +
                  ", ".join(f"{k}: {v}" for k, v in sorted(cov.items(), key=lambda kv: -kv[1]))]
    return "\n".join(lines)
