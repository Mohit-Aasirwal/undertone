"""User idle time (X11 via libXss) and the screensaver-mode state machine."""
import ctypes
import os

_xss = None


def _x11_idle_seconds():
    global _xss
    if _xss is None:
        try:
            x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
            xss = ctypes.cdll.LoadLibrary("libXss.so.1")
        except OSError:
            _xss = False
            return 0.0

        class XScreenSaverInfo(ctypes.Structure):
            _fields_ = [("window", ctypes.c_ulong), ("state", ctypes.c_int), ("kind", ctypes.c_int),
                        ("til_or_since", ctypes.c_ulong), ("idle", ctypes.c_ulong), ("eventMask", ctypes.c_ulong)]
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x11.XDefaultRootWindow.restype = ctypes.c_ulong
        xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)
        xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(XScreenSaverInfo)]
        dpy = x11.XOpenDisplay(None)
        if not dpy:
            _xss = False
            return 0.0
        _xss = (x11, xss, dpy, x11.XDefaultRootWindow(dpy), xss.XScreenSaverAllocInfo())
    if _xss is False:
        return 0.0
    x11, xss, dpy, root, info = _xss
    if not xss.XScreenSaverQueryInfo(dpy, root, info):
        return 0.0
    return info.contents.idle / 1000.0


def idle_seconds():
    """Seconds since the last input event. UNDERTONE_FAKE_IDLE (a number, or a file holding one) overrides."""
    fake = os.environ.get("UNDERTONE_FAKE_IDLE")
    if fake:
        try:
            if os.path.isfile(fake):
                with open(fake) as f:
                    fake = f.read().strip()
            return float(fake)
        except (OSError, ValueError):
            return 0.0
    try:
        return max(0.0, _x11_idle_seconds())
    except Exception:
        return 0.0


class Screensaver:
    """Calls on_change(True) once idle passes the threshold and on_change(False) once activity resumes."""

    def __init__(self, idle_minutes, on_change):
        self.threshold = float(idle_minutes) * 60 if idle_minutes else 0
        self.on_change = on_change
        self.active = False

    def update(self, idle):
        if self.threshold <= 0:
            return
        if not self.active and idle >= self.threshold:
            self.active = True
            self.on_change(True)
        elif self.active and idle < self.threshold:
            self.active = False
            self.on_change(False)
