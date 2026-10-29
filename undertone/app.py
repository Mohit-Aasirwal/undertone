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
from .lyrics import current_line_index, lyrics_from_response, word_progress  # noqa: E402
from .sources import EMPTY, fetch_chain  # noqa: E402
from .translate import translate_lines  # noqa: E402
from .backdrop import ken_burns_scale  # noqa: E402
from .idle import Screensaver, idle_seconds  # noqa: E402
from .stats import DB_PATH, MIN_PLAY_S, History, format_report  # noqa: E402
from .web import NowPlayingServer, snapshot_payload  # noqa: E402
from .wayland import layer_margins, load_layer_shell, session_type, wants_layer_shell  # noqa: E402
from .artcheck import ArtRegistry  # noqa: E402
from .player import pick_playing, track_from_metadata  # noqa: E402
from .visualizer import band_levels, smooth_levels  # noqa: E402
from .modes import DRAWERS, MODES  # noqa: E402
from .control import ControlService, ctl_main  # noqa: E402
from .beat import OnsetDetector  # noqa: E402
from .offsets import Offsets  # noqa: E402
from .theme import FALLBACK_ACCENT, FALLBACK_BASE, gtk_accent, palette_from_pixbuf  # noqa: E402

CACHE_DIR = os.path.expanduser("~/.cache/undertone")
POLL_MS = 250
HIDE_GRACE_S = 3.0
RETRY_S = 20.0
FRAME_MS = 33
DEFAULT_VISUALIZER = {"enabled": True, "rings": 10, "opacity": 0.2, "mode": "rings", "fps": 30}
MPRIS_PREFIX = "org.mpris.MediaPlayer2."
USER_AGENT = f"undertone/{__version__} (https://github.com/Mohit-Aasirwal/undertone)"
AUTOSTART = os.path.expanduser("~/.config/autostart/undertone.desktop")
OFFSETS_PATH = os.path.join(os.path.dirname(CONFIG_PATH), "offsets.json")
DEFAULT_THEME = {"source": "art"}  # art | gtk | none
DEFAULT_TRANSLATION = {"enabled": False, "target": "hi"}
DEFAULT_BACKDROP = {"motion": True}
DEFAULT_SCREENSAVER = {"enabled": False, "idle_minutes": 10}
DEFAULT_WEB = {"enabled": False, "port": 8765, "bind": "0.0.0.0"}
IDLE_POLL_MS = 2000
MOTION_MS = 500
TRANSLATION_CACHE = os.path.join(CACHE_DIR, "translations.json")


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


DEFAULT_LYRICS = {"sources": ["local", "lrclib", "netease"], "local_dirs": ["~/Music"]}


def fetch_lyrics(track, sources=DEFAULT_LYRICS["sources"], local_dirs=DEFAULT_LYRICS["local_dirs"]):
    """Cached lookup through the configured source chain. Local files are never cached (they may change)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.sha1(repr(track.key).encode()).hexdigest()
    path = os.path.join(CACHE_DIR, key + ".json")
    if "local" in sources:
        from .sources import read_local
        data = read_local(track, local_dirs)
        if data:
            return lyrics_from_response(data)
    remote = [x for x in sources if x != "local"]
    if not remote:
        return lyrics_from_response(dict(EMPTY))
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        # entries cached before 1.0 carry no source; they all came from LRCLIB
        data.setdefault("source", "lrclib" if (data.get("syncedLyrics") or data.get("plainLyrics")
                                               or data.get("instrumental")) else "none")
        return lyrics_from_response(data)
    data = fetch_chain(track, remote, local_dirs)
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
        self.detector = OnsetDetector(self.RATE / self.FRAME)
        freqs = np.linspace(0, self.RATE / 2, self.FRAME // 2 + 1)
        self.bass_bins = (freqs >= 40) & (freqs < 150)
        self.bass_ref = 1e-9
        self.pulse = 0.0
        self.bpm = 0
        self.capture_state = "starting"
        self.lock = threading.Lock()
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        window = np.hanning(self.FRAME)
        # UNDERTONE_AUDIO_CMD replaces parec with any command that writes f32le mono 48 kHz to stdout
        override = os.environ.get("UNDERTONE_AUDIO_CMD")
        cmd = override or ("parec --device=@DEFAULT_MONITOR@ --format=float32le "
                           f"--rate={self.RATE} --channels=1 --latency-msec=40 --raw")
        while True:
            try:
                proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                print("parec not found; visualizer disabled", file=sys.stderr)
                self.capture_state = "parec missing"
                return
            self.capture_state = "running"
            while True:
                buf = proc.stdout.read(self.FRAME * 4)
                if len(buf) < self.FRAME * 4:
                    break
                samples = np.frombuffer(buf, np.float32)
                mag = np.abs(np.fft.rfft(samples * window))
                # slowly decaying running peak so quiet passages still move the rings
                self.reference = max(float(mag.max()), self.reference * 0.995, 1e-6)
                new = band_levels(mag, self.RATE, self.n_bands, reference=self.reference)
                # beats come from linear bass energy against its own slow peak: the dB-scaled bands
                # that drive the visuals compress a kick's jump too much for real music
                bass = float(np.mean(mag[self.bass_bins]))
                self.bass_ref = max(bass, self.bass_ref * 0.995, 1e-9)
                self.detector.feed(bass / self.bass_ref)
                with self.lock:
                    self.levels = smooth_levels(self.levels, new, attack=0.6, decay=0.12)
                    self.pulse, self.bpm = self.detector.pulse(), self.detector.tempo_bpm()
            proc.wait()
            self.capture_state = f"exited ({proc.returncode}), retrying"
            with self.lock:
                self.levels, self.pulse, self.bpm = np.zeros(self.n_bands), 0.0, 0
            if override:
                self.capture_state = "test feed ended"
                return  # a test feed ended; nothing to reconnect to
            time.sleep(2)  # sink went away or parec died: retry

    def snapshot(self):
        with self.lock:
            return {"levels": self.levels.copy(), "pulse": self.pulse, "bpm": self.bpm}


class Playback:
    """Polls MPRIS, loads lyrics and art, and shows/hides every Lightbox window."""

    def __init__(self, windows, audio=None, players=None, theme=None, vis_mode="rings", lyrics_cfg=None,
                 translation=None, backdrop=None, screensaver=None, history_path=DB_PATH, web=None,
                 frame_rate=30):
        self.windows = windows
        self.frame_rate = frame_rate
        self.art_png = None  # PNG bytes of the current art for the web page
        self.art_registry = ArtRegistry(os.path.join(CACHE_DIR, "art-seen.json"))
        self.fps_mark = (time.monotonic(), [0] * len(windows))
        web = {**DEFAULT_WEB, **(web or {})}
        self.web = None
        if web["enabled"]:
            try:
                self.web = NowPlayingServer(web["bind"], int(web["port"]), self.web_payload, self.web_art)
                self.web.start()
            except OSError as e:
                print(f"web page disabled: cannot listen on {web['bind']}:{web['port']} ({e})", file=sys.stderr)
        self.history = History(history_path)
        self.played_s = 0.0  # seconds of the current track actually heard
        self.last_tick = None
        ss = {**DEFAULT_SCREENSAVER, **(screensaver or {})}
        self.screensaver = Screensaver(ss["idle_minutes"] if ss["enabled"] else 0, self.set_raised)
        self.raised = False
        self.backdrop = {**DEFAULT_BACKDROP, **(backdrop or {})}
        self.kb_scale = 1.0
        self.started_at = time.monotonic()
        self.lyrics_cfg = {**DEFAULT_LYRICS, **(lyrics_cfg or {})}
        self.translation = {**DEFAULT_TRANSLATION, **(translation or {})}
        self.translations = None  # list parallel to lyrics.synced (or plain lines), or None
        self.audio = audio
        self.vis_mode = vis_mode if vis_mode in MODES else MODES[0]
        self.theme_source = (theme or DEFAULT_THEME)["source"]
        self.theme = {"accent": gtk_accent() if self.theme_source == "gtk" else FALLBACK_ACCENT, "base": FALLBACK_BASE}
        players = players or {}
        self.mpris = Mpris(players.get("allow"), players.get("deny"))
        self.track = None
        self.lyrics = None
        self.art = None
        self.pos = 0.0
        self.pos_at = time.monotonic()
        self.last_playing_at = 0.0
        self.loading = False
        self.offsets = Offsets(OFFSETS_PATH)
        self.hidden_by_user = False
        self.vis_state = {}  # per-mode scratch (wave phase, particle field)
        self.control = ControlService({
            "Toggle": self.toggle, "Show": lambda: self.set_hidden(False), "Hide": lambda: self.set_hidden(True),
            "CycleVisualizer": self.cycle_visualizer, "Nudge": self.nudge, "SetOffset": self.set_offset,
            "SetGlobalOffset": self.set_global_offset, "Status": self.status,
        })
        GLib.timeout_add(POLL_MS, self.poll)
        if audio:
            GLib.timeout_add(int(1000 / max(5, min(60, self.frame_rate))), self.animate)
        if self.backdrop["motion"]:
            GLib.timeout_add(MOTION_MS, self.drift)
        if self.screensaver.threshold > 0:
            GLib.timeout_add(IDLE_POLL_MS, self.check_idle)

    def check_idle(self):
        self.screensaver.update(idle_seconds())
        return True

    def set_raised(self, raised):
        """Screensaver mode: lift the windows above everything while idle, back to the desktop layer after."""
        self.raised = raised
        for win in self.windows:
            win.set_layer(raised)
            if self.track and not self.hidden_by_user:
                win.show_all()

    # ---- control surface -------------------------------------------------
    def set_hidden(self, hidden):
        self.hidden_by_user = hidden
        for win in self.windows:
            (win.hide if hidden or not self.track else win.show_all)()

    def toggle(self):
        self.set_hidden(not self.hidden_by_user)

    def cycle_visualizer(self):
        self.vis_mode = MODES[(MODES.index(self.vis_mode) + 1) % len(MODES)]
        self.redraw()
        return self.vis_mode

    def nudge(self, ms):
        if not self.track:
            raise RuntimeError("nothing is playing")
        return self.offsets.nudge(self.track.key, ms)

    def set_offset(self, ms):
        if not self.track:
            raise RuntimeError("nothing is playing")
        self.offsets.set(self.track.key, ms)

    def set_global_offset(self, ms):
        self.offsets.global_ms = ms

    def status(self):
        t = self.track
        now = time.monotonic()
        then, counts = self.fps_mark
        fps = [round((w.frames - c) / max(now - then, 1e-6), 1) for w, c in zip(self.windows, counts)]
        self.fps_mark = (now, [w.frames for w in self.windows])
        audio = self.audio.snapshot() if self.audio else None
        return {
            "visible": any(w.get_visible() for w in self.windows),
            "hidden_by_user": self.hidden_by_user,
            "track": {"title": t.title, "artist": t.artist, "album": t.album, "length_s": t.length_us / 1e6} if t else None,
            "position_s": round(self.position(), 3) if t else None,
            "offset_ms": self.offsets.get(t.key) if t else None,
            "global_offset_ms": self.offsets.global_ms,
            "lyrics": (None if self.lyrics is None else
                       "synced" if self.lyrics.synced else "plain" if self.lyrics.plain else
                       "instrumental" if self.lyrics.instrumental else "none"),
            "lyrics_source": self.lyrics.source if self.lyrics else None,
            "art": self.art is not None,
            "translated": self.translations is not None,
            "backdrop_scale": round(self.kb_scale, 4),
            "screensaver": self.raised,
            "played_s": round(self.played_s),
            "web": f"http://{self.web.httpd.server_address[0]}:{self.web.port}/" if self.web else None,
            "visualizer": self.vis_mode,
            "accent": "#%02x%02x%02x" % tuple(int(c * 255) for c in self.theme["accent"]),
            "bpm": self.audio.bpm if self.audio else None,
            "pulse": round(self.audio.pulse, 3) if self.audio else None,
            "audio_level": round(float(np.mean(audio["levels"])), 3) if audio is not None and len(audio["levels"]) else None,
            "audio_capture": self.audio.capture_state if self.audio else None,
            "fps": fps,
        }

    def lines_and_idx(self):
        """Lyric lines and the current index, independent of any window (shared by the web page)."""
        ly = self.lyrics
        if not self.track or ly is None:
            return [], -1
        if ly.synced:
            return [t for _, t in ly.synced], current_line_index(ly.synced, self.position())
        if ly.plain:
            lines = ly.plain.splitlines()
            frac = self.position() / max(self.track.length_us / 1_000_000, 1)
            return lines, min(int(frac * len(lines)), len(lines) - 1)
        return [], -1

    def web_payload(self):
        lines, idx = self.lines_and_idx()
        return snapshot_payload(self.status(), lines, idx, self.art_png is not None, self.translations)

    def web_art(self):
        return (self.art_png, "image/png") if self.art_png else None

    def finish_play(self):
        """Log the track that just ended if it was listened to for long enough to count."""
        if self.track and self.played_s >= MIN_PLAY_S:
            try:
                self.history.record(self.track, round(self.played_s), self.lyrics.source if self.lyrics else "none")
            except Exception as e:
                print("history write failed:", e, file=sys.stderr)
        self.played_s = 0.0

    def drift(self):
        """Advance the backdrop zoom and repaint whole windows; between ticks every partial redraw
        reuses the same scale, so the moving centre never tears against the static edges."""
        if self.track:
            self.kb_scale = ken_burns_scale(time.monotonic() - self.started_at)
            self.redraw()
        return True

    def animate(self):
        if self.track:
            pulse_q = round(self.audio.pulse * 40) if self.audio else 0  # the line scale in 1/40 steps
            for win in self.windows:
                if win.scroll:
                    win.area.queue_draw()
                else:
                    win.area.queue_draw_area(*win.ring_bounds())
                    if pulse_q != win.last_pulse_q:  # the band only changes when the beat scale does
                        win.area.queue_draw_area(*win.current_line_bounds())
                win.last_pulse_q = pulse_q
        return True

    def poll(self):
        track, pos = self.mpris.snapshot()
        now = time.monotonic()
        if track:
            self.last_playing_at = now
            self.pos, self.pos_at = pos, now
            if self.track is None or track.key != self.track.key:
                self.finish_play()
                self.track, self.lyrics, self.art, self.translations = track, None, None, None
                self.started_at = now
                self.loading = True
                threading.Thread(target=self.load_for, args=(track,), daemon=True).start()
            elif self.last_tick is not None:
                self.played_s += now - self.last_tick
            self.last_tick = now
            for win in self.windows:
                if not win.get_visible() and not self.hidden_by_user:
                    win.show_all()
        elif self.track and now - self.last_playing_at > HIDE_GRACE_S:
            for win in self.windows:
                win.hide()
            self.finish_play()
            self.track = None
        if not track:
            self.last_tick = None
        self.redraw()
        return True

    def redraw(self):
        for win in self.windows:
            win.area.queue_draw()

    def load_for(self, track):
        try:
            lyrics = fetch_lyrics(track, self.lyrics_cfg["sources"], self.lyrics_cfg["local_dirs"])
        except Exception as e:  # transient or unexpected: show a notice and retry
            print("lyrics unavailable, retrying later:", e, file=sys.stderr)
            lyrics = None
        art = load_art(track.art_url)
        if art is not None:
            digest = hashlib.sha1(art.get_pixels()).hexdigest()
            if self.art_registry.note(digest, track.artist):
                print(f"ignoring placeholder art for {track.title!r}", file=sys.stderr)
                art = None
        palette = None
        if art is not None and self.theme_source == "art":
            try:
                palette = palette_from_pixbuf(art)
            except Exception as e:
                print("palette extraction failed:", e, file=sys.stderr)
        png = None
        if art is not None and self.web is not None:
            ok, data = art.save_to_bufferv("png", [], [])
            png = bytes(data) if ok else None
        GLib.idle_add(self.apply_loaded, track, lyrics, art, palette, png)
        if lyrics and self.translation["enabled"] and (lyrics.synced or lyrics.plain):
            lines = [t for _, t in lyrics.synced] if lyrics.synced else lyrics.plain.splitlines()
            translated = translate_lines(lines, self.translation["target"], TRANSLATION_CACHE)
            if translated is None:
                print("translation unavailable", file=sys.stderr)
            GLib.idle_add(self.apply_translation, track, translated)

    def apply_translation(self, track, translated):
        if self.track and self.track.key == track.key:
            self.translations = translated
            self.redraw()
        return False

    def retry_for(self, track):
        if self.track and self.track.key == track.key and self.lyrics is None:
            threading.Thread(target=self.load_for, args=(track,), daemon=True).start()
        return False

    def apply_loaded(self, track, lyrics, art, palette=None, png=None):
        if self.track and self.track.key == track.key:
            self.lyrics, self.art, self.loading = lyrics, art, False
            self.art_png = png
            if self.theme_source == "art":
                self.theme = palette or {"accent": FALLBACK_ACCENT, "base": FALLBACK_BASE}
            if lyrics is None:
                GLib.timeout_add(int(RETRY_S * 1000), self.retry_for, track)
            self.redraw()
        return False

    def position(self):
        raw = self.pos + (time.monotonic() - self.pos_at)
        return raw + (self.offsets.total_seconds(self.track.key) if self.track else 0.0)


class Lightbox(Gtk.Window):
    """One full-screen desktop-layer window per monitor; all draw from the shared Playback."""

    def __init__(self, box, scale, visualizer=None, monitor=None):
        super().__init__(title="Undertone")
        self.visualizer = visualizer
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.stick()
        self.layer_shell = load_layer_shell() if wants_layer_shell(session_type(), True) else None
        if self.layer_shell:
            # Wayland: a layer-shell surface on this monitor, placed by margins from its top-left corner
            ls = self.layer_shell
            ls.init_for_window(self)
            ls.set_namespace(self, "undertone")
            ls.set_keyboard_mode(self, ls.KeyboardMode.NONE)
            ls.set_exclusive_zone(self, -1)
            if monitor is not None:
                ls.set_monitor(self, monitor["gdk"])
                left, top = layer_margins(box, monitor["geom"])
                ls.set_margin(self, ls.Edge.LEFT, left)
                ls.set_margin(self, ls.Edge.TOP, top)
            ls.set_anchor(self, ls.Edge.LEFT, True)
            ls.set_anchor(self, ls.Edge.TOP, True)
        self.set_layer(raised=False)
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
        self.cur_extent = (0, 0)  # x and width of the current line's ink, reference coordinates
        self.frames = 0  # draw calls, for the fps readout in status
        self.last_pulse_q = -1
        self.static_cache = None  # (key, surface): the header, never scrolls
        self.line_pos = {}        # line index -> vertical centre in the most recent layout
        self.scroll = None        # {"start": t, "delta": px} while lines glide to the new current line
        self.bg_cache = None    # (key, surface) of the dimmed art backdrop
        self.text_cache = None  # (key, surface) of header + lyrics; re-rendered when the line changes

    def set_layer(self, raised):
        """Desktop layer (below everything) normally; above everything in screensaver mode."""
        if self.layer_shell:
            ls = self.layer_shell
            ls.set_layer(self, ls.Layer.TOP if raised else ls.Layer.BACKGROUND)
            return
        # X11: the type hint only takes effect on map, so a mapped window is re-mapped
        was_visible = self.get_visible()
        if was_visible:
            self.hide()
        self.set_type_hint(Gdk.WindowTypeHint.NORMAL if raised else Gdk.WindowTypeHint.DESKTOP)
        if was_visible:
            self.show_all()
        # _NET_WM_STATE hints are sent as client messages once mapped, so set them after the re-map;
        # the skip/sticky hints are unchanged at the GTK level, so resend them via the GdkWindow
        self.set_keep_above(raised)
        self.set_keep_below(not raised)
        gdk_win = self.get_window()
        if gdk_win is not None:
            gdk_win.set_skip_taskbar_hint(True)
            gdk_win.set_skip_pager_hint(True)
            gdk_win.stick()

    track = property(lambda self: self.state.track)
    theme = property(lambda self: self.state.theme)
    translations = property(lambda self: self.state.translations)
    lyrics = property(lambda self: self.state.lyrics)
    art = property(lambda self: self.state.art)
    loading = property(lambda self: self.state.loading)

    def position(self):
        return self.state.position()

    # ---- drawing ---------------------------------------------------------
    def on_draw(self, widget, cr):
        self.frames += 1
        # Draw in 1080p reference coordinates; one transform scales fonts and spacing together.
        cr.scale(self.scale, self.scale)
        w, h = widget.get_allocated_width() / self.scale, widget.get_allocated_height() / self.scale
        self.draw_background(cr, w, h)
        if not self.track:
            return
        audio = self.state.audio.snapshot() if self.state.audio else {"levels": [], "pulse": 0.0, "bpm": 0}
        if self.visualizer and self.state.audio:
            cx, cy, max_r = self.ring_geometry(w, h)
            DRAWERS[self.state.vis_mode](cr, cx, cy, max_r, audio["levels"], audio["pulse"],
                                         self.theme["accent"], self.visualizer["opacity"], self.state.vis_state)
        self.draw_text_layer(cr, w, h, audio["pulse"])

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

    LYRICS_TOP, LYRICS_MARGIN = 230, 160
    SCROLL_S = 0.38

    def draw_text_layer(self, cr, w, h, pulse=0.0):
        """Three cached layers: the header; the other lines (glide on line change);
        the current line (beat-scaled, karaoke-clipped)."""
        dw, dh = round(w * self.scale), round(h * self.scale)
        notice, lines, idx, highlight = self.lyrics_content()
        skey = (self.track.key, id(self.art), dw, dh, self.theme["accent"], bool(notice), self.full_visual())
        if not self.static_cache or self.static_cache[0] != skey:
            surface = cr.get_target().create_similar(cairo.Content.COLOR_ALPHA, dw, dh)
            sc = cairo.Context(surface)
            sc.scale(self.scale, self.scale)
            self.draw_header(sc, w)
            if notice:
                self.draw_notice(sc, w, h, notice)
            self.static_cache = (skey, surface)
        cr.save()
        cr.identity_matrix()
        cr.set_source_surface(self.static_cache[1], 0, 0)
        cr.paint()
        cr.restore()
        if notice:
            return

        key = (self.track.key, id(self.lyrics), idx, dw, dh, self.theme["accent"], id(self.translations))
        if not self.text_cache or self.text_cache[0] != key:
            prev = self.text_cache
            self.line_pos = {}
            surface = cr.get_target().create_similar(cairo.Content.COLOR_ALPHA, dw, dh)
            tc = cairo.Context(surface)
            tc.scale(self.scale, self.scale)
            cur_cy = self.draw_lyrics(tc, w, h, lines, idx, highlight, part="others")
            cur_surface = None
            if highlight and idx >= 0:
                cur_surface = cr.get_target().create_similar(cairo.Content.COLOR_ALPHA, dw, dh)
                cc = cairo.Context(cur_surface)
                cc.scale(self.scale, self.scale)
                self.draw_lyrics(cc, w, h, lines, idx, highlight, part="current")
            # same track and lyrics, new line: glide from where the new line sat in the old layout,
            # and cross-fade the outgoing line from accent to grey at its new position
            if prev and prev[0][:2] == key[:2] and idx in prev[5] and highlight:
                old_idx = prev[0][2]
                self.scroll = {"start": time.monotonic(), "delta": prev[5][idx] - prev[3],
                               "old_surface": prev[2], "old_cy": prev[3],
                               "old_new_cy": self.line_pos.get(old_idx)}
            self.text_cache = (key, surface, cur_surface, cur_cy, self.cur_extent, dict(self.line_pos))
        _, surface, cur_surface, cur_cy, (ex0, ew), _ = self.text_cache

        offset, fade = 0.0, 0.0
        if self.scroll:
            p = min(1.0, (time.monotonic() - self.scroll["start"]) / self.SCROLL_S)
            offset = self.scroll["delta"] * (1 - p) ** 3  # ease-out: fast start, soft landing
            fade = (1 - p) ** 2                            # outgoing accent line fades out
            if p >= 1.0:
                self.scroll = None
        cr.save()
        cr.identity_matrix()
        cr.rectangle(0, (self.LYRICS_TOP - 12) * self.scale, dw, dh)  # never glide over the header
        cr.clip()
        cr.translate(0, offset * self.scale)
        cr.set_source_surface(surface, 0, 0)
        cr.paint()
        if self.scroll and fade > 0.01 and self.scroll.get("old_surface") is not None \
                and self.scroll.get("old_new_cy") is not None:
            # the old line, still in accent and large, shrinking and fading over its grey successor
            old = self.scroll
            cy_new = old["old_new_cy"] * self.scale
            shrink = 1.0 - 0.29 * (1 - fade)  # Sans Bold 34 -> Sans 24
            cr.save()
            cr.translate(dw / 2, cy_new)
            cr.scale(shrink, shrink)
            cr.translate(-dw / 2, -old["old_cy"] * self.scale)
            cr.set_source_surface(old["old_surface"], 0, 0)
            cr.paint_with_alpha(fade)
            cr.restore()
        if cur_surface is not None:
            k = 1.0 + 0.04 * pulse
            cx, cy = dw / 2, cur_cy * self.scale
            cr.translate(cx, cy)
            cr.scale(k, k)
            cr.translate(-cx, -cy)
            cr.set_source_surface(cur_surface, 0, 0)
            progress = self.karaoke_progress(idx)
            if progress >= 1.0:
                cr.paint()
            else:  # karaoke: dim whole line, then the sung part at full strength
                cr.paint_with_alpha(0.4)
                cr.rectangle(ex0 * self.scale, 0, ew * self.scale * progress, dh)
                cr.clip()
                cr.paint()
        cr.restore()

    def current_line_bounds(self):
        """Device-pixel band around the current line, repainted every frame for the beat scale."""
        cy = self.text_cache[3] if self.text_cache else 0
        band = 70
        return (0, int((cy - band) * self.scale), int(self.area.get_allocated_width()), int(2 * band * self.scale) + 2)

    def karaoke_progress(self, idx):
        ly = self.lyrics
        if not ly or not ly.words or idx < 0 or idx >= len(ly.words) or not ly.words[idx]:
            return 1.0
        line_end = ly.synced[idx + 1][0] if idx + 1 < len(ly.synced) else ly.synced[idx][0] + 5.0
        return word_progress(ly.words[idx], self.position(), line_end)

    def draw_background(self, cr, w, h):
        """Paint the dimmed art backdrop from a cached surface; re-render only when art or size changes."""
        dw, dh = round(w * self.scale), round(h * self.scale)
        key = (id(self.art), dw, dh, self.theme["base"])
        if not self.bg_cache or self.bg_cache[0] != key:
            surface = cr.get_target().create_similar(cairo.Content.COLOR, dw, dh)
            bc = cairo.Context(surface)
            bc.scale(self.scale, self.scale)
            self.render_background(bc, w, h)
            self.bg_cache = (key, surface)
        cr.save()
        cr.identity_matrix()
        k = self.state.kb_scale
        if k != 1.0:
            cr.translate(dw / 2, dh / 2)
            cr.scale(k, k)
            cr.translate(-dw / 2, -dh / 2)
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
        # soft radial glow in the art's base tint, centred on the lyrics area
        br, bg, bb = self.theme["base"]
        glow = cairo.RadialGradient(w / 2, h * 0.6, 0, w / 2, h * 0.6, max(w, h) * 0.7)
        glow.add_color_stop_rgba(0, br, bg, bb, 0.9)
        glow.add_color_stop_rgba(1, br, bg, bb, 0.0)
        cr.set_source(glow)
        cr.paint()

    def ring_geometry(self, w, h):
        if self.full_visual():  # nothing to read: give the visualizer the whole area
            cx, cy = w / 2, h / 2
            return cx, cy, min(w / 2, h / 2) - 40
        top = 230
        cx, cy = w / 2, top + (h - top) / 2
        max_r = min(w / 2, h - cy, cy) - 30
        return cx, cy, max_r

    def full_visual(self):
        ly = self.lyrics
        return bool(self.track) and not self.loading and ly is not None and not (ly.synced or ly.plain)

    def ring_bounds(self):
        """Device-pixel rectangle the rings can touch; the per-frame redraw is clipped to it."""
        w, h = self.area.get_allocated_width() / self.scale, self.area.get_allocated_height() / self.scale
        cx, cy, max_r = self.ring_geometry(w, h)
        r = max_r + 4
        return (int((cx - r) * self.scale), int((cy - r) * self.scale),
                int(2 * r * self.scale) + 2, int(2 * r * self.scale) + 2)

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
        layout.set_width((w - x - 80) * Pango.SCALE)
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

    def draw_lyrics(self, cr, w, h, lines, idx, highlight, part="all"):
        """Draw lines centred on the current one. `part` selects "all", "others" or just "current".
        Returns the current line's vertical centre."""
        top, margin = self.LYRICS_TOP, self.LYRICS_MARGIN
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
            self.line_pos[i] = yy + hh / 2
            if part != "current":
                self.draw_line(cr, layout, lines[i], margin, yy, False, highlight, (y - yy) / (centre_y - top))
        # current and below
        yy = y
        for i in range(cur, len(lines)):
            if yy > h:
                break
            hh = height_of(i)
            self.line_pos[i] = yy + hh / 2
            is_cur = highlight and i == idx
            if part == "all" or (part == "current") == is_cur:
                self.draw_line(cr, layout, lines[i], margin, yy, is_cur, highlight, (yy - y) / (h - centre_y))
            yy += hh + gap
            if is_cur and part != "current":
                yy += self.draw_translation(cr, layout, i, margin, yy)
        return y + height_of(cur) / 2

    def draw_translation(self, cr, layout, i, x, y):
        """A faint translated line under the current one; returns the height consumed."""
        tr = self.translations
        if not tr or i >= len(tr) or not tr[i]:
            return 0
        layout.set_font_description(Pango.FontDescription("Sans 20"))
        layout.set_text(tr[i], -1)
        cr.set_source_rgba(1, 1, 1, 0.55)
        cr.move_to(x, y - 8)
        PangoCairo.show_layout(cr, layout)
        return layout.get_pixel_size()[1] + 6

    def draw_line(self, cr, layout, text, x, y, is_cur, highlight, dist):
        layout.set_font_description(Pango.FontDescription("Sans Bold 34") if is_cur else Pango.FontDescription("Sans 24"))
        layout.set_text(text or "♪", -1)
        if is_cur:
            ink, _logical = layout.get_pixel_extents()
            self.cur_extent = (x + ink.x, ink.width)
            # soft glow: the accent at low alpha, offset around the glyphs, then the crisp line on top
            cr.set_source_rgba(*self.theme["accent"], 0.22)
            for dx, dy in ((0, 2.5), (2.5, 0), (0, -2.5), (-2.5, 0), (1.8, 1.8), (-1.8, -1.8)):
                cr.move_to(x + dx, y + dy)
                PangoCairo.show_layout(cr, layout)
            cr.set_source_rgba(*self.theme["accent"], 1.0)
        elif highlight:
            cr.set_source_rgba(1, 1, 1, max(0.12, 0.55 - 0.45 * min(dist, 1.0)))
        else:
            cr.set_source_rgba(1, 1, 1, 0.75)
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)

    def draw_notice(self, cr, w, h, text):
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription("Sans 26"))
        layout.set_text(text, -1)
        tw, th = layout.get_pixel_size()
        cr.set_source_rgba(1, 1, 1, 0.45)
        ny = h - th - 48 if self.full_visual() else (h - th) / 2  # keep the centre for the visualizer
        cr.move_to((w - tw) / 2, ny)
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
                    "geom": (g.x, g.y, g.width, g.height), "gdk": m})
    return out


USAGE = f"""undertone {__version__} — desktop-layer lyrics with an audio-reactive visualizer

usage: undertone [--list-monitors | --install-autostart | --uninstall-autostart | --version]
       undertone ctl toggle|show|hide|cycle-vis|nudge <ms>|offset <ms>|global-offset <ms>|status
       undertone stats [--days N]        listening history (default 7 days; --days 0 for all time)

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
    if argv and argv[0] == "ctl":
        return ctl_main(argv[1:])
    if argv and argv[0] == "stats":
        days = 7
        if "--days" in argv:
            days = int(argv[argv.index("--days") + 1]) or None
        db = History(os.environ.get("UNDERTONE_HISTORY") or DB_PATH)
        print(format_report(db.report(days=days), days=days))
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
    theme = {**DEFAULT_THEME, **config.get("theme", {})}
    windows = []
    for m in select_monitors(mons, config.get("monitors", "all")):
        wc = window_config_for(config, m)
        box = resolve_box(m["geom"], wc["width"], wc["height"], wc["ratio"], wc["anchor"], wc["margin"])
        scale = wc["scale"] or box[3] / 1080
        windows.append(Lightbox(box, scale, vis if vis["enabled"] else None, monitor=m))
    if not windows:
        sys.exit("undertone: no monitors matched the config; try --list-monitors")
    audio = AudioLevels(int(vis["rings"])) if vis["enabled"] else None
    state = Playback(windows, audio, config.get("players"), theme, vis["mode"], config.get("lyrics"),
                     config.get("translation"), config.get("backdrop"), config.get("screensaver"),
                     os.environ.get("UNDERTONE_HISTORY") or DB_PATH, config.get("web"), int(vis["fps"]))
    for win in windows:
        win.state = state
        win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()
