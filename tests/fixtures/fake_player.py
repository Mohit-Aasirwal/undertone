#!/usr/bin/env python3
"""A minimal MPRIS player on the session bus for end-to-end tests.

    python3 tests/fixtures/fake_player.py --title "Song" --artist "Band" --length 200 [--status Playing]

Position advances in real time while Playing. Control it over D-Bus like any player:
    dbus-send --session --dest=org.mpris.MediaPlayer2.undertonetest /org/mpris/MediaPlayer2 \
        org.mpris.MediaPlayer2.Player.Pause
"""
import argparse
import time

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS_NAME = "org.mpris.MediaPlayer2.undertonetest"
XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <property name="Identity" type="s" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Play"/><method name="Pause"/><method name="PlayPause"/><method name="Stop"/>
    <method name="SetPosition"><arg type="o" name="TrackId" direction="in"/><arg type="x" name="Position" direction="in"/></method>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Position" type="x" access="read"/>
  </interface>
</node>
"""


class FakePlayer:
    def __init__(self, args):
        self.status = args.status
        self.meta = {
            "mpris:trackid": GLib.Variant("o", "/org/undertonetest/track/1"),
            "xesam:title": GLib.Variant("s", args.title),
            "xesam:artist": GLib.Variant("as", [args.artist]),
            "xesam:album": GLib.Variant("s", args.album),
            "mpris:length": GLib.Variant("x", int(args.length * 1_000_000)),
        }
        if args.art:
            self.meta["mpris:artUrl"] = GLib.Variant("s", args.art)
        if args.url:
            self.meta["xesam:url"] = GLib.Variant("s", args.url)
        self.pos_us = int(args.start * 1_000_000)
        self.pos_at = time.monotonic()

    def position(self):
        if self.status == "Playing":
            return self.pos_us + int((time.monotonic() - self.pos_at) * 1_000_000)
        return self.pos_us

    def set_status(self, status):
        self.pos_us, self.pos_at = self.position(), time.monotonic()
        self.status = status

    def on_call(self, conn, sender, path, iface, method, params, inv):
        if method == "Play":
            self.set_status("Playing")
        elif method == "Pause":
            self.set_status("Paused")
        elif method == "PlayPause":
            self.set_status("Paused" if self.status == "Playing" else "Playing")
        elif method == "Stop":
            self.set_status("Stopped")
        elif method == "SetPosition":
            self.pos_us, self.pos_at = params.unpack()[1], time.monotonic()
        inv.return_value(None)

    def on_get(self, conn, sender, path, iface, prop):
        if prop == "Identity":
            return GLib.Variant("s", "Undertone test player")
        if prop == "PlaybackStatus":
            return GLib.Variant("s", self.status)
        if prop == "Metadata":
            return GLib.Variant("a{sv}", self.meta)
        if prop == "Position":
            return GLib.Variant("x", self.position())
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="Test Song")
    ap.add_argument("--artist", default="Test Artist")
    ap.add_argument("--album", default="Test Album")
    ap.add_argument("--length", type=float, default=200.0)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--status", default="Playing")
    ap.add_argument("--art", default="")
    ap.add_argument("--url", default="")
    args = ap.parse_args()
    player = FakePlayer(args)
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    info = Gio.DBusNodeInfo.new_for_xml(XML)
    for iface in info.interfaces:
        bus.register_object("/org/mpris/MediaPlayer2", iface, player.on_call, player.on_get, None)
    Gio.bus_own_name_on_connection(bus, BUS_NAME, Gio.BusNameOwnerFlags.NONE, None, None)
    print(f"fake player up as {BUS_NAME}", flush=True)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
