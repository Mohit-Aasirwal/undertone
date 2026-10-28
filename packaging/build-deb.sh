#!/usr/bin/env bash
# Build undertone_<version>_all.deb into dist/. Needs only dpkg-deb (no build-essential).
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(python3 -c "import undertone; print(undertone.__version__)")
PKG=undertone_${VERSION}_all
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT

SITE="$ROOT/usr/lib/python3/dist-packages/undertone"
mkdir -p "$SITE" "$ROOT/usr/bin" "$ROOT/usr/share/doc/undertone" "$ROOT/usr/share/applications" "$ROOT/DEBIAN"
cp undertone/*.py "$SITE/"
cp README.md CHANGELOG.md config.example.toml "$ROOT/usr/share/doc/undertone/"
cat > "$ROOT/usr/bin/undertone" <<'SH'
#!/usr/bin/python3
from undertone.app import main
main()
SH
chmod 755 "$ROOT/usr/bin/undertone"
cat > "$ROOT/usr/share/applications/undertone.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Undertone
Comment=Desktop-layer lyrics with an audio-reactive visualizer
Exec=undertone
Icon=audio-x-generic
Categories=AudioVideo;Audio;
Terminal=false
DESK
cat > "$ROOT/DEBIAN/control" <<CTRL
Package: undertone
Version: $VERSION
Section: sound
Priority: optional
Architecture: all
Depends: python3 (>= 3.11), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, python3-numpy, pulseaudio-utils
Recommends: gir1.2-gtklayershell-0.1
Maintainer: Mohit Aasirwal
Homepage: https://github.com/Mohit-Aasirwal/undertone
Description: Desktop-layer lyrics lightbox with an audio-reactive visualizer
 Undertone shows time-synced lyrics for whatever MPRIS player is playing,
 between your wallpaper and your windows, with album-art theming, beat
 detection and concentric-ring, bar, wave and particle visualizers.
CTRL
mkdir -p dist
dpkg-deb --root-owner-group --build "$ROOT" "dist/$PKG.deb" >/dev/null
echo "built dist/$PKG.deb"
