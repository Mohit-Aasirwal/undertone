#!/usr/bin/env bash
# Installs Undertone on Debian/Ubuntu/Mint: system GTK bindings via apt, the app via pipx.
set -euo pipefail
cd "$(dirname "$0")"

if command -v apt-get >/dev/null; then
  sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-numpy pulseaudio-utils pipx
else
  echo "Install these from your distro first: PyGObject (GTK 3), pycairo, numpy, parec (pulseaudio-utils), pipx" >&2
fi

pipx install --system-site-packages --force .
pipx ensurepath >/dev/null 2>&1 || true

mkdir -p ~/.config/undertone
[ -f ~/.config/undertone/config.toml ] || cp config.example.toml ~/.config/undertone/config.toml

echo
echo "Installed. Start it with:  undertone"
echo "Start on login with:       undertone --install-autostart"
echo "Config:                    ~/.config/undertone/config.toml"
