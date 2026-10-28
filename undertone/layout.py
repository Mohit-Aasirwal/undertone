"""Pure layout logic: which monitors to use and where the lyrics box sits on each."""
import os
import tomllib

CONFIG_PATH = os.environ.get("UNDERTONE_CONFIG") or os.path.expanduser("~/.config/undertone/config.toml")

DEFAULT_WINDOW = {
    "width": "fill",     # "fill", pixels (1280) or percent of the monitor ("70%")
    "height": None,      # same forms as width; None derives from ratio, or fills
    "ratio": None,       # "16:9", "4:3", "1:1"... used when height is None
    "anchor": "center",  # center, top, bottom, left, right, top-left, top-right, bottom-left, bottom-right
    "margin": 0,         # gap in pixels between the box and the monitor edge
    "scale": None,       # text/UI scale; None means proportional to box height (1.0 at 1080px)
}


def load_config(path=CONFIG_PATH):
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def select_monitors(monitors, spec):
    if spec == "all":
        return list(monitors)
    if spec == "primary":
        return [m for m in monitors if m["primary"]] or monitors[:1]
    out = []
    for want in spec:
        for m in monitors:
            if want == m["index"] or want == m["name"]:
                out.append(m)
    return out


def _dim(value, full):
    if value is None or value == "fill":
        return full
    if isinstance(value, str) and value.endswith("%"):
        return round(full * float(value[:-1]) / 100)
    return int(value)


def _ratio(text):
    a, b = text.split(":")
    return float(a) / float(b)


def resolve_box(geom, width, height, ratio, anchor, margin):
    mx, my, mw, mh = geom
    avail_w, avail_h = mw - 2 * margin, mh - 2 * margin
    w = _dim(width, avail_w)
    if height is not None:
        h = _dim(height, avail_h)
    elif ratio:
        h = round(w / _ratio(ratio))
        if h > avail_h:
            h = avail_h
            w = round(h * _ratio(ratio))
    else:
        h = avail_h
    w, h = min(w, avail_w), min(h, avail_h)

    vert, _, horiz = anchor.partition("-") if "-" in anchor else (anchor, "", "")
    if anchor in ("left", "right"):
        vert, horiz = "center", anchor
    xs = {"left": margin, "right": mw - margin - w}
    ys = {"top": margin, "bottom": mh - margin - h}
    x = xs.get(horiz, (mw - w) / 2)
    y = ys.get(vert, (mh - h) / 2)
    return (mx + round(x), my + round(y), w, h)


def window_config_for(config, monitor):
    section = config.get("window", {})
    merged = dict(DEFAULT_WINDOW)
    merged.update({k: v for k, v in section.items() if not isinstance(v, dict)})
    for key in (str(monitor["index"]), monitor["name"]):
        if isinstance(section.get(key), dict):
            merged.update(section[key])
    return merged
