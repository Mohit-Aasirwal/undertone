"""Wayland support through gtk-layer-shell (optional). On X11 the DESKTOP type hint does the job."""
import os


def wants_layer_shell(session_type, available):
    return session_type == "wayland" and bool(available)


def layer_margins(box, monitor):
    """Top-left margins that place `box` (x, y, w, h) on `monitor` (x, y, w, h) when anchored top-left."""
    return (box[0] - monitor[0], box[1] - monitor[1])


def load_layer_shell():
    """The GtkLayerShell namespace if the bindings exist and the compositor supports the protocol."""
    try:
        import gi
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
    except (ValueError, ImportError):
        return None
    try:
        return GtkLayerShell if GtkLayerShell.is_supported() else None
    except Exception:
        return None


def session_type():
    return os.environ.get("XDG_SESSION_TYPE", "x11").lower()
