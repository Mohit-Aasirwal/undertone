# Flathub submission

Everything Flathub needs is here; it has not been built on the maintainer's machine yet
(no flatpak-builder available there), so the first build happens on your box or in the Flathub PR.

1. Build and run locally once:
   ```bash
   flatpak install flathub org.gnome.Platform//47 org.gnome.Sdk//47
   flatpak-builder --user --install --force-clean build-dir packaging/io.github.mohitaasirwal.Undertone.yml
   flatpak run io.github.mohitaasirwal.Undertone
   ```
   `parec` is not in the GNOME runtime: the visualizer needs the PulseAudio socket (granted) and the
   `pulseaudio-utils` binary. If it is missing inside the sandbox, add a `pulseaudio` module that builds
   only `parec`, or switch `UNDERTONE_AUDIO_CMD` to `pw-cat --record --format f32 --rate 48000 --channels 1 -`.
2. Fork https://github.com/flathub/flathub, create branch `new-pr`, add the manifest, the three files in
   this directory and a `flathub.json` with `{"only-arches": ["x86_64", "aarch64"]}`.
3. Open the PR against `flathub/flathub:new-pr`. The bot builds it; address review notes, then the app
   gets its own repo under the flathub org and publishes within a day.
