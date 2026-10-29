"""Colour theming: an accent and a dark base from album art, or the GTK theme's accent."""
import colorsys

import numpy as np

FALLBACK_ACCENT = (0.85, 0.85, 0.88)
FALLBACK_BASE = (0.05, 0.05, 0.07)


def _rgb_to_hsv(px):
    r, g, b = px[:, 0], px[:, 1], px[:, 2]
    mx, mn = px.max(axis=1), px.min(axis=1)
    delta = mx - mn
    v = mx
    s = np.where(mx > 0, delta / np.maximum(mx, 1e-9), 0)
    h = np.zeros_like(mx)
    nz = delta > 1e-9
    rc = np.where(nz, (mx - r) / np.maximum(delta, 1e-9), 0)
    gc = np.where(nz, (mx - g) / np.maximum(delta, 1e-9), 0)
    bc = np.where(nz, (mx - b) / np.maximum(delta, 1e-9), 0)
    h = np.where(mx == r, bc - gc, np.where(mx == g, 2.0 + rc - bc, 4.0 + gc - rc))
    h = np.where(nz, (h / 6.0) % 1.0, 0)
    return h, s, v


def palette_from_pixels(pixels, bins=24):
    """Pick the most common vivid hue; brighten it for text on a dark backdrop.

    `pixels` is an (N, 3) array, floats 0..1 or uint8."""
    px = np.asarray(pixels, dtype=float).reshape(-1, 3)
    if px.max() > 1.0:
        px = px / 255.0
    base = tuple(float(c) for c in np.clip(px.mean(axis=0) * 0.3, 0, 0.3)) if len(px) else FALLBACK_BASE
    h, s, v = _rgb_to_hsv(px)
    vivid = (s > 0.25) & (v > 0.15) & (v < 0.98)
    if vivid.sum() < max(1, 0.02 * len(px)):
        return {"accent": FALLBACK_ACCENT, "accent2": FALLBACK_ACCENT, "base": base}
    weights = (s * v)[vivid]
    hist, edges = np.histogram(h[vivid], bins=bins, range=(0, 1), weights=weights)
    top = int(np.argmax(hist))

    def bin_colour(b):
        sel = vivid & (h >= edges[b]) & (h < edges[b + 1] + (1e-9 if b == bins - 1 else 0))
        hh, ss, vv = colorsys.rgb_to_hsv(*px[sel].mean(axis=0))
        return tuple(float(c) for c in colorsys.hsv_to_rgb(hh, min(ss, 0.7), max(vv, 0.9)))

    accent = bin_colour(top)
    # second accent: the strongest hue at least ~55 degrees away, else a hue-shifted sibling
    far = [(hist[b], b) for b in range(bins) if hist[b] > 0.08 * hist[top]
           and min(abs(b - top), bins - abs(b - top)) >= round(0.15 * bins)]
    if far:
        accent2 = bin_colour(max(far)[1])
    else:
        hh, ss, vv = colorsys.rgb_to_hsv(*accent)
        accent2 = tuple(float(c) for c in colorsys.hsv_to_rgb((hh + 0.08) % 1.0, min(ss, 0.6), max(vv, 0.9)))
    return {"accent": accent, "accent2": accent2, "base": base}


def palette_from_pixbuf(pixbuf, sample=64):
    """Downscale a GdkPixbuf and extract its palette."""
    small = pixbuf.scale_simple(sample, sample, 2)  # 2 = GdkPixbuf.InterpType.BILINEAR
    data = np.frombuffer(small.get_pixels(), dtype=np.uint8)
    stride, channels = small.get_rowstride(), small.get_n_channels()
    rows = data.reshape(-1)[: stride * sample].reshape(sample, stride)[:, : sample * channels]
    return palette_from_pixels(rows.reshape(-1, channels)[:, :3])


def sibling(accent):
    """A hue-shifted companion for a single accent (used when only one colour is known)."""
    if accent == FALLBACK_ACCENT:
        return FALLBACK_ACCENT
    hh, ss, vv = colorsys.rgb_to_hsv(*accent)
    return tuple(float(c) for c in colorsys.hsv_to_rgb((hh + 0.08) % 1.0, min(ss, 0.6), max(vv, 0.9)))


def gtk_accent():
    """The running GTK theme's selection colour, or the neutral fallback."""
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        ctx = Gtk.Window().get_style_context()
        for name in ("accent_bg_color", "theme_selected_bg_color", "selected_bg_color"):
            ok, color = ctx.lookup_color(name)
            if ok:
                hh, ss, vv = colorsys.rgb_to_hsv(color.red, color.green, color.blue)
                return tuple(float(c) for c in colorsys.hsv_to_rgb(hh, min(ss, 0.7), max(vv, 0.9)))
    except Exception:
        pass
    return FALLBACK_ACCENT
