# Changelog

## 1.1.0 — 2026-10-28

- Beat detection now works on real music: onsets come from linear bass energy instead of the
  dB-scaled bands, which compressed a kick's jump so much that almost nothing fired.
- Fixed a visible seam on the current line: the per-frame redraw covered only the ring area, so the
  beat-scaled line was repainted at two different scales. The redraw now covers the line's band too.
- Lines glide upward on a line change (ease-out, 380 ms) instead of jumping.
- Glassmorphic look: a frosted card behind the lyrics, a chip behind the header, a specular edge
  tinted by the accent, and a soft glow on the current line.
- Rings mode fills each annulus with a translucent radial gradient that brightens toward the ring.
- `undertone ctl status` reports `fps` per window, `audio_level` and `audio_capture`.

## 1.0.0 — 2026-10-28

A major release: everything below is new since 0.1.0.

### Visual
- Colour theming from the album cover (or your GTK theme's accent): current line, visualizer tint and a backdrop glow.
- Beat detection: rings kick outward and the current line pulses on onsets; tempo shown in `ctl status`.
- Four visualizer modes: rings, bars, wave, particles. Cycle at runtime with `undertone ctl cycle-vis`.
- Word-level karaoke sweep for enhanced LRC lyrics (`<mm:ss.xx>` word tags).
- Optional translation of the current line (Google Translate web endpoint), any target language.
- Slow Ken Burns zoom on the art backdrop.
- Tracks without lyrics give the whole area to the visualizer.

### Smarter behaviour
- Player allow/deny lists so a YouTube video or podcast tab doesn't trigger a lyrics search.
- Lyrics source chain: local `.lrc` files (beside the track or in `local_dirs`), LRCLIB, NetEase. Source shown in status.
- Lyric offsets: global and per-track, persisted; nudge live with `undertone ctl nudge <ms>`.
- D-Bus control interface (`org.undertone`) and the `undertone ctl` client: toggle, show, hide, cycle-vis, nudge, offset, status.
- Screensaver mode: lifts the lyrics above every window after N idle minutes, drops back on activity.

### Reach
- Listening history in SQLite and `undertone stats [--days N]`.
- Shared listening page: a tiny web server mirrors the lyrics live to any browser on your network.
- Wayland support via gtk-layer-shell when the bindings are installed (untested on the release machine).
- Packaging: `.deb` built in CI and attached to releases, an AUR `PKGBUILD`, and a Flatpak manifest.

### Also
- A fake MPRIS player fixture and `UNDERTONE_AUDIO_CMD` for deterministic end-to-end testing.
- Fixed the 30 fps animation timer, which had been silently inactive.

## 0.1.0 — 2026-10-28

First release.

- Desktop-layer lyrics window that appears while any MPRIS player is playing and hides when it stops.
- Time-synced lyrics from LRCLIB with a duration-tolerant search fallback, plain-lyrics fallback, and local cache.
- Album-art backdrop and header.
- Concentric ring visualizer driven by the system audio output (PipeWire/PulseAudio via `parec`).
- Multi-monitor support with per-monitor size, aspect ratio, anchor, margin and text scale.
- `--list-monitors`, `--install-autostart`, `--uninstall-autostart`.
