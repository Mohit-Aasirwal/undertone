# Undertone

Lyrics that live underneath your windows.

Undertone turns your desktop into a lyrics lightbox whenever music plays. It sits on the desktop layer, above the wallpaper and below every window, so it is there when you glance at an empty desktop and out of the way when you are working. Time-synced lyrics scroll with the track, the album art fades in behind them, and ten faint concentric rings pulse with the audio.

![Undertone showing synced lyrics with the ring visualizer](docs/screenshot.png)

## What it does

- Watches every MPRIS player on the session bus: Spotify (app or web), YouTube Music, VLC, Firefox, Chromium-based browsers.
- Shows the lightbox while something is playing and hides it a few seconds after playback stops.
- Fetches time-synced lyrics from [LRCLIB](https://lrclib.net) (free, no API key), falls back to a duration-tolerant search and then to plain lyrics, and caches everything locally.
- Draws the current line large and bright with neighbours fading by distance.
- Listens to the system audio output and drives a concentric ring visualizer: inner rings follow bass, outer rings follow treble.
- Supports several monitors, each with its own size, aspect ratio, anchor and text scale.

## Requirements

- Linux with an X11 session and a compositing window manager (tested on Linux Mint 22 / Cinnamon).
- Python 3.11 or newer.
- GTK 3 bindings for Python (`python3-gi`, `gir1.2-gtk-3.0`), `pycairo`, `numpy`.
- `parec` from `pulseaudio-utils`, which works with both PulseAudio and PipeWire.

## Install

```bash
git clone https://github.com/Mohit-Aasirwal/undertone.git
cd undertone
./install.sh
```

The installer uses apt for the GTK bindings and `pipx` for the app itself. Without apt, install the requirements above with your distro's package manager and run `pipx install --system-site-packages .`.

Then:

```bash
undertone                       # run in the foreground
undertone --install-autostart   # start on login
undertone --list-monitors       # names and indices for the config
```

Or run straight from the checkout with `python3 -m undertone`.

## Configure

Copy `config.example.toml` to `~/.config/undertone/config.toml` and edit. Every option is documented in the file.

```toml
monitors = "all"            # "primary", or ["HDMI-A-0"], or [0, 1]

[window]
width  = "fill"             # "fill", 1280, or "70%"
# ratio = "16:9"            # derive height from an aspect ratio
anchor = "center"           # top, bottom, left, right, top-left, bottom-right...
margin = 0

[window.DP-1-0]             # per-monitor override, by name or index
width = "60%"
ratio = "16:9"
anchor = "bottom-right"
margin = 40

[visualizer]
enabled = true
rings = 10
opacity = 0.2
```

Text and spacing scale with the box height automatically. Set `scale` to pin them.

## How it works

Playback state comes from MPRIS over D-Bus, polled four times a second. Lyrics are looked up on LRCLIB by artist, title, album and duration. The visualizer streams the default sink's monitor through `parec`, runs a 2048-sample FFT, and maps it to log-spaced bands with a slowly decaying running peak for auto-gain. Each monitor gets a GTK window with the `DESKTOP` type hint, which places it between the wallpaper and your other windows.

## Development

```bash
python3 -m unittest discover -s tests -t .
```

The parsing, layout, player-selection and visualizer math live in pure modules with unit tests. The GTK window and D-Bus code are in `undertone/app.py`.

## License

MIT
