"""Runtime control over D-Bus: the in-app service and the `undertone ctl` client."""
import json
import sys

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS_NAME = "org.undertone"
OBJECT_PATH = "/org/undertone"
INTERFACE = "org.undertone.Control"
XML = f"""
<node>
  <interface name="{INTERFACE}">
    <method name="Toggle"/>
    <method name="Show"/>
    <method name="Hide"/>
    <method name="CycleVisualizer"><arg type="s" name="mode" direction="out"/></method>
    <method name="Nudge"><arg type="i" name="ms" direction="in"/><arg type="i" name="total" direction="out"/></method>
    <method name="SetOffset"><arg type="i" name="ms" direction="in"/></method>
    <method name="SetGlobalOffset"><arg type="i" name="ms" direction="in"/></method>
    <method name="Status"><arg type="s" name="json" direction="out"/></method>
  </interface>
</node>
"""
OUT_SIG = {"CycleVisualizer": "(s)", "Nudge": "(i)", "Status": "(s)"}
COMMANDS = {
    "toggle": ("Toggle", 0), "show": ("Show", 0), "hide": ("Hide", 0), "cycle-vis": ("CycleVisualizer", 0),
    "nudge": ("Nudge", 1), "offset": ("SetOffset", 1), "global-offset": ("SetGlobalOffset", 1), "status": ("Status", 0),
}


def parse_ctl(argv):
    if not argv or argv[0] not in COMMANDS:
        raise ValueError("usage: undertone ctl " + "|".join(COMMANDS))
    method, nargs = COMMANDS[argv[0]]
    if len(argv) - 1 != nargs:
        raise ValueError(f"{argv[0]} takes {nargs} argument(s)")
    try:
        args = [int(a) for a in argv[1:]]
    except ValueError:
        raise ValueError(f"{argv[0]} expects a whole number of milliseconds") from None
    return method, args


class ControlService:
    """Owns org.undertone and dispatches method calls to plain Python callables."""

    def __init__(self, handlers):
        self.handlers = handlers
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        node = Gio.DBusNodeInfo.new_for_xml(XML)
        self.bus.register_object(OBJECT_PATH, node.interfaces[0], self.on_call, None, None)
        Gio.bus_own_name_on_connection(self.bus, BUS_NAME, Gio.BusNameOwnerFlags.REPLACE, None, None)

    def on_call(self, conn, sender, path, iface, method, params, invocation):
        try:
            result = self.handlers[method](*params.unpack())
        except Exception as e:  # report to the caller instead of crashing the UI loop
            invocation.return_dbus_error("org.undertone.Error", str(e))
            return
        sig = OUT_SIG.get(method)
        if sig == "(s)" and not isinstance(result, str):
            result = json.dumps(result)
        invocation.return_value(GLib.Variant(sig, (result,)) if sig else None)


def call(method, args=()):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    sig = {"Nudge": "(i)", "SetOffset": "(i)", "SetGlobalOffset": "(i)"}.get(method)
    params = GLib.Variant(sig, tuple(args)) if sig else None
    res = bus.call_sync(BUS_NAME, OBJECT_PATH, INTERFACE, method, params, None, Gio.DBusCallFlags.NONE, 2000, None)
    return res.unpack()[0] if res and res.n_children() else None


def ctl_main(argv):
    try:
        method, args = parse_ctl(argv)
    except ValueError as e:
        sys.exit(str(e))
    try:
        result = call(method, args)
    except GLib.Error as e:
        sys.exit("undertone is not running" if "ServiceUnknown" in str(e) else f"control call failed: {e.message}")
    if result is not None:
        print(result)
