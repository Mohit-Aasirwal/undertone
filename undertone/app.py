"""Undertone: a desktop-layer lyrics lightbox with an audio-reactive ring visualizer."""
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

import cairo
import numpy as np
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from . import __version__  # noqa: E402
from .layout import CONFIG_PATH, load_config, resolve_box, select_monitors, window_config_for  # noqa: E402
from .lyrics import (Lyrics, current_line_index, lrclib_search_url, lrclib_url,  # noqa: E402
                     lyrics_from_response, pick_search_result)
from .player import pick_playing, track_from_metadata  # noqa: E402
from .visualizer import band_levels, ring_radii, smooth_levels  # noqa: E402

CACHE_DIR = os.path.expanduser("~/.cache/undertone")
POLL_MS = 250
HIDE_GRACE_S = 3.0
RETRY_S = 20.0
FRAME_MS = 33
DEFAULT_VISUALIZER = {"enabled": True, "rings": 10, "opacity": 0.2}
MPRIS_PREFIX = "org.mpris.MediaPlayer2."
USER_AGENT = f"undertone/{__version__} (https://github.com/Mohit-Aasirwal/undertone)"
AUTOSTART = os.path.expanduser("~/.config/autostart/undertone.desktop")


class Mpris:
    def __init__(self, allow=None, deny=None):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.allow, self.deny = allow or [], deny or []

    def _props(self, name, prop):
        res = self.bus.call_sync(
            name, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", ("org.mpris.MediaPlayer2.Player", prop)),
            None, Gio.DBusCallFlags.NONE, 500, None)
        return res.unpack()[0]

    def players(self):
        res = self.bus.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames",
            None, None, Gio.DBusCallFlags.NONE, 500, None)
        return [n for n in res.unpack()[0] if n.startswith(MPRIS_PREFIX)]

    def snapshot(self):
        """Return (track, position_seconds) for the first playing player, or (None, 0)."""
        statuses = {}
        for name in self.players():
            try:
                statuses[name] = self._props(name, "PlaybackStatus")
            except GLib.Error:
                continue
        name = pick_playing(statuses, self.allow, self.deny)
        if not name:
            return None, 0.0
        try:
            track = track_from_metadata(self._props(name, "Metadata"))
            pos = self._props(name, "Position") / 1_000_000
        except GLib.Error:
            return None, 0.0
        return track, pos


class LyricsUnavailable(Exception):
    """Transient failure (network, 5xx): worth retrying while the track still plays."""


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def fetch_lyrics(track):
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.sha1(repr(track.key).encode()).hexdigest()
    path = os.path.join(CACHE_DIR, key + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return lyrics_from_response(json.load(f))
    duration_s = round(track.length_us / 1_000_000)
    try:
        try:
            data = _get_json(lrclib_url(track.artist, track.title, track.album, track.length_us))
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            data = pick_search_result(_get_json(lrclib_search_url(track.artist, track.title)), duration_s) \
                or {"syncedLyrics": None, "plainLyrics": None, "instrumental": False}
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise LyricsUnavailable(str(e)) from e
    with open(path, "w") as f:
        json.dump(data, f)
    return lyrics_from_response(data)


def load_art(url):
    if not url:
        return None
    try:
        if url.startswith("file://"):
            return GdkPixbuf.Pixbuf.new_from_file(url[7:])
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as r:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(r.read())
            loader.close()
            return loader.get_pixbuf()
    except Exception:
        return None


class AudioLevels:
    """Streams the default sink's monitor through parec and keeps smoothed per-band levels."""
    RATE, FRAME = 48000, 2048

    def __init__(self, n_bands):
        self.n_bands = n_bands
        self.levels = np.zeros(n_bands)
        self.reference = 1e-6
        self.lock = threading.Lock()
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        window = np.hanning(self.FRAME)
        cmd = ["parec", "--device=@DEFAULT_MONITOR@", "--format=float32le", f"--rate={self.RATE}",
               "--channels=1", "--latency-msec=40", "--raw"]
        while True:
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                print("parec not found; visualizer disabled", file=sys.stderr)
                return
            while True:
                buf = proc.stdout.read(self.FRAME * 4)
                if len(buf) < self.FRAME * 4:
                    break
                samples = np.frombuffer(buf, np.float32)
                mag = np.abs(np.fft.rfft(samples * window))
                # slowly decaying running peak so quiet passages still move the rings
                self.reference = max(float(mag.max()), self.reference * 0.995, 1e-6)
                new = band_levels(mag, self.RATE, self.n_bands, reference=self.reference)
                with self.lock:
                    self.levels = smooth_levels(self.levels, new, attack=0.6, decay=0.12)
            proc.wait()
            with self.lock:
                self.levels = np.zeros(self.n_bands)
            time.sleep(2)  # sink went away or parec died: retry

    def snapshot(self):
        with self.lock:
            return self.levels.copy()


class Playback:
    """Polls MPRIS, loads lyrics and art, and shows/hides every Lightbox window."""

    def __init__(self, windows, audio=None, players=None):
        self.windows = windows
        self.audio = audio
        players = players or {}
        self.mpris = Mpris(players.get("allow"), players.get("deny"))
        self.track = None
        self.lyrics = None
        self.art = None
        self.pos = 0.0
        self.pos_at = time.monotonic()
        self.last_playing_at = 0.0
        self.loading = False
        GLib.timeout_add(POLL_MS, self.poll)
        if audio:
            GLib.timeout_add(FRAME_MS, self.animate)

    def animate(self):
        if self.track:
            for win in self.windows:
                win.area.queue_draw_area(*win.ring_bounds())
        return True

    def poll(self):
        track, pos = self.mpris.snapshot()
        now = time.monotonic()
        if track:
            self.last_playing_at = now
            self.pos, self.pos_at = pos, now
            if self.track is None or track.key != self.track.key:
                self.track, self.lyrics, self.art = track, None, None
                self.loading = True
                threading.Thread(target=self.load_for, args=(track,), daemon=True).start()
            for win in self.windows:
                if not win.get_visible():
                    win.show_all()
        elif self.track and now - self.last_playing_at > HIDE_GRACE_S:
            for win in self.windows:
                win.hide()
            self.track = None
        self.redraw()
        return True

    def redraw(self):
        for win in self.windows:
            win.area.queue_draw()

    def load_for(self, track):
        try:
            lyrics = fetch_lyrics(track)
        except Exception as e:  # transient or unexpected: show a notice and retry
            print("lyrics unavailable, retrying later:", e, file=sys.stderr)
            lyrics = None
        art = load_art(track.art_url)
        GLib.idle_add(self.apply_loaded, track, lyrics, art)

    def retry_for(self, track):
        if self.track and self.track.key == track.key and self.lyrics is None:
            threading.Thread(target=self.load_for, args=(track,), daemon=True).start()
        return False

    def apply_loaded(self, track, lyrics, art):
        if self.track and self.track.key == track.key:
            self.lyrics, self.art, self.loading = lyrics, art, False
            if lyrics is None:
                GLib.timeout_add(int(RETRY_S * 1000), self.retry_for, track)
            self.redraw()
        return False

    def position(self):
        return self.pos + (time.monotonic() - self.pos_at)


class Lightbox(Gtk.Window):
    """One full-screen desktop-layer window per monitor; all draw from the shared Playback."""

    def __init__(self, box, scale, visualizer=None):
        super().__init__(title="Undertone")
        self.visualizer = visualizer
        self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_keep_below(True)
        self.stick()
        self.set_app_paintable(True)
        screen = self.get_screen()
        if screen.get_rgba_visual():
            self.set_visual(screen.get_rgba_visual())

        x, y, w, h = box
        self.scale = scale
        self.move(x, y)
        self.set_default_size(w, h)
        self.resize(w, h)
        self.set_size_request(w, h)

        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self.on_draw)
        self.add(self.area)
        self.state = None
        self.bg_cache = None    # (key, surface) of the dimmed art backdrop
        self.text_cache = None  # (key, surface) of header + lyrics; re-rendered when the line changes

    track = property(lambda self: self.state.track)
    lyrics = property(lambda self: self.state.lyrics)
    art = property(lambda self: self.state.art)
    loading = property(lambda self: self.state.loading)

    def position(self):
        return self.state.position()

    # ---- drawing ---------------------------------------------------------
    def on_draw(self, widget, cr):
        # Draw in 1080p reference coordinates; one transform scales fonts and spacing together.
        cr.scale(self.scale, self.scale)
        w, h = widget.get_allocated_width() / self.scale, widget.get_allocated_height() / self.scale
        self.draw_background(cr, w, h)
        if not self.track:
            return
        if self.visualizer and self.state.audio:
            self.draw_rings(cr, w, h, self.state.audio.snapshot())
        self.draw_text_layer(cr, w, h)

    def lyrics_content(self):
        """What the lyrics area should show right now: (notice, lines, idx, highlight)."""
        if self.loading:
            return ("Fetching lyrics…", None, -1, False)
        ly = self.lyrics
        if ly is None:
            return ("Lyrics service busy, retrying…", None, -1, False)
        if ly.instrumental:
            return ("♪ Instrumental", None, -1, False)
        if ly.synced:
            return (None, [t for _, t in ly.synced], current_line_index(ly.synced, self.position()), True)
        if ly.plain:
            lines = ly.plain.splitlines()
            frac = self.position() / max(self.track.length_us / 1_000_000, 1)
            return (None, lines, min(int(frac * len(lines)), len(lines) - 1), False)
        return ("No lyrics found", None, -1, False)

    def draw_text_layer(self, cr, w, h):
        dw, dh = round(w * self.scale), round(h * self.scale)
        notice, lines, idx, highlight = self.lyrics_content()
        key = (self.track.key, id(self.lyrics), id(self.art), notice, idx, dw, dh)
        if not self.text_cache or self.text_cache[0] != key:
            surface = cr.get_target().create_similar(cairo.Content.COLOR_ALPHA, dw, dh)
            tc = cairo.Context(surface)
            tc.scale(self.scale, self.scale)
            self.draw_header(tc, w)
            if notice:
                self.draw_notice(tc, w, h, notice)
            else:
                self.draw_lyrics(tc, w, h, lines, idx, highlight)
            self.text_cache = (key, surface)
        cr.save()
        cr.identity_matrix()
        cr.set_source_surface(self.text_cache[1], 0, 0)
        cr.paint()
        cr.restore()

    def draw_background(self, cr, w, h):
        """Paint the dimmed art backdrop from a cached surface; re-render only when art or size changes."""
        dw, dh = round(w * self.scale), round(h * self.scale)
        key = (id(self.art), dw, dh)
        if not self.bg_cache or self.bg_cache[0] != key:
            surface = cr.get_target().create_similar(cairo.Content.COLOR, dw, dh)
            bc = cairo.Context(surface)
            bc.scale(self.scale, self.scale)
            self.render_background(bc, w, h)
            self.bg_cache = (key, surface)
        cr.save()
        cr.identity_matrix()
        cr.set_source_surface(self.bg_cache[1], 0, 0)
        cr.paint()
        cr.restore()

    def render_background(self, cr, w, h):
        cr.set_source_rgb(0.05, 0.05, 0.07)
        cr.paint()
        if self.art:
            scale = max(w / self.art.get_width(), h / self.art.get_height())
            cr.save()
            cr.translate((w - self.art.get_width() * scale) / 2, (h - self.art.get_height() * scale) / 2)
            cr.scale(scale, scale)
            Gdk.cairo_set_source_pixbuf(cr, self.art, 0, 0)
            cr.paint_with_alpha(0.18)
            cr.restore()
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.paint()

    def ring_geometry(self, w, h):
        top = 230
        cx, cy = w / 2, top + (h - top) / 2
        max_r = min(w / 2, h - cy, cy) - 30
        return cx, cy, max_r

    def ring_bounds(self):
        """Device-pixel rectangle the rings can touch; the per-frame redraw is clipped to it."""
        w, h = self.area.get_allocated_width() / self.scale, self.area.get_allocated_height() / self.scale
        cx, cy, max_r = self.ring_geometry(w, h)
        r = max_r + 4
        return (int((cx - r) * self.scale), int((cy - r) * self.scale),
                int(2 * r * self.scale) + 2, int(2 * r * self.scale) + 2)

    def draw_rings(self, cr, w, h, levels):
        cx, cy, max_r = self.ring_geometry(w, h)
        n = len(levels)
        base = max_r * 0.22
        spacing = (max_r - base) / max(n, 1)
        opacity = self.visualizer["opacity"]
        for r, level in zip(ring_radii(levels, base, spacing, spacing * 0.9), levels):
            cr.set_source_rgba(0.85, 0.85, 0.88, opacity * (0.35 + 0.65 * float(level)))
            cr.set_line_width(1.0 + 2.5 * float(level))
            cr.new_sub_path()
            cr.arc(cx, cy, float(r), 0, 2 * math.pi)
            cr.stroke()

    def draw_header(self, cr, w):
        x, y, size = 64, 56, 120
        if self.art:
            thumb = self.art.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
            rounded_rect(cr, x, y, size, size, 12)
            cr.save()
            cr.clip()
            Gdk.cairo_set_source_pixbuf(cr, thumb, x, y)
            cr.paint()
            cr.restore()
            x += size + 28
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription("Sans Bold 22"))
        layout.set_text(self.track.title, -1)
        layout.set_width((w - x - 64) * Pango.SCALE)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.move_to(x, y + 22)
        PangoCairo.show_layout(cr, layout)
        layout.set_font_description(Pango.FontDescription("Sans 15"))
        sub = self.track.artist + (f"  ·  {self.track.album}" if self.track.album else "")
        layout.set_text(sub, -1)
        cr.set_source_rgba(1, 1, 1, 0.6)
        cr.move_to(x, y + 66)
        PangoCairo.show_layout(cr, layout)

    def draw_lyrics(self, cr, w, h, lines, idx, highlight):
        top, margin = 230, 160
        centre_y = top + (h - top) / 2
        layout = PangoCairo.create_layout(cr)
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_width((w - 2 * margin) * Pango.SCALE)
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        big, small = Pango.FontDescription("Sans Bold 34"), Pango.FontDescription("Sans 24")
        gap = 22

        def height_of(i):
            layout.set_font_description(big if (highlight and i == idx) else small)
            layout.set_text(lines[i] or "♪", -1)
            return layout.get_pixel_size()[1]

        cur = max(idx, 0)
        y = centre_y - height_of(cur) / 2
        # above
        yy = y
        for i in range(cur - 1, -1, -1):
            hh = height_of(i)
            yy -= hh + gap
            if yy + hh < top:
                break
            self.draw_line(cr, layout, lines[i], margin, yy, False, highlight, (y - yy) / (centre_y - top))
        # current and below
        yy = y
        for i in range(cur, len(lines)):
            if yy > h:
                break
            hh = height_of(i)
            is_cur = highlight and i == idx
            self.draw_line(cr, layout, lines[i], margin, yy, is_cur, highlight, (yy - y) / (h - centre_y))
            yy += hh + gap

    def draw_line(self, cr, layout, text, x, y, is_cur, highlight, dist):
        layout.set_font_description(Pango.FontDescription("Sans Bold 34") if is_cur else Pango.FontDescription("Sans 24"))
        layout.set_text(text or "♪", -1)
        if is_cur:
            alpha = 1.0
        elif highlight:
            alpha = max(0.12, 0.55 - 0.45 * min(dist, 1.0))
        else:
            alpha = 0.75
        cr.set_source_rgba(1, 1, 1, alpha)
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)

    def draw_notice(self, cr, w, h, text):
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription("Sans 26"))
        layout.set_text(text, -1)
        tw, th = layout.get_pixel_size()
        cr.set_source_rgba(1, 1, 1, 0.45)
        cr.move_to((w - tw) / 2, (h - th) / 2)
        PangoCairo.show_layout(cr, layout)


def rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def monitors():
    display = Gdk.Display.get_default()
    out = []
    for i in range(display.get_n_monitors()):
        m = display.get_monitor(i)
        g = m.get_geometry()
        out.append({"index": i, "name": m.get_model() or f"monitor{i}", "primary": m.is_primary(),
                    "geom": (g.x, g.y, g.width, g.height)})
    return out


USAGE = f"""undertone {__version__} — desktop-layer lyrics with an audio-reactive visualizer

usage: undertone [--list-monitors | --install-autostart | --uninstall-autostart | --version]

Runs until killed. Config: {CONFIG_PATH}
"""


def launch_command():
    exe = shutil.which("undertone")
    return exe if exe else f"{sys.executable} -m undertone"


def install_autostart():
    os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
    with open(AUTOSTART, "w") as f:
        f.write("[Desktop Entry]\nType=Application\nName=Undertone\n"
                "Comment=Desktop-layer lyrics for whatever is playing\n"
                f"Exec={launch_command()}\nX-GNOME-Autostart-enabled=true\n"
                "X-GNOME-Autostart-Delay=5\nNoDisplay=true\n")
    print(f"autostart entry written to {AUTOSTART}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    GLib.set_prgname("undertone")  # stable WM_CLASS whether run as a script or `python -m undertone`
    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return
    if "--version" in argv:
        print(__version__)
        return
    if "--install-autostart" in argv:
        return install_autostart()
    if "--uninstall-autostart" in argv:
        if os.path.exists(AUTOSTART):
            os.remove(AUTOSTART)
        print(f"removed {AUTOSTART}")
        return
    mons = monitors()
    if "--list-monitors" in argv:
        for m in mons:
            x, y, w, h = m["geom"]
            print(f'{m["index"]}  {m["name"]:<12} {w}x{h} at +{x}+{y}{"  (primary)" if m["primary"] else ""}')
        return
    config = load_config()
    vis = {**DEFAULT_VISUALIZER, **config.get("visualizer", {})}
    windows = []
    for m in select_monitors(mons, config.get("monitors", "all")):
        wc = window_config_for(config, m)
        box = resolve_box(m["geom"], wc["width"], wc["height"], wc["ratio"], wc["anchor"], wc["margin"])
        scale = wc["scale"] or box[3] / 1080
        windows.append(Lightbox(box, scale, vis if vis["enabled"] else None))
    if not windows:
        sys.exit("undertone: no monitors matched the config; try --list-monitors")
    audio = AudioLevels(int(vis["rings"])) if vis["enabled"] else None
    state = Playback(windows, audio, config.get("players"))
    for win in windows:
        win.state = state
        win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()
