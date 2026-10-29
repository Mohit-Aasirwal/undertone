"""Editing helpers for .lrc files: formatting, shifting, retiming, tap-to-mark."""
import re

_TS = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
_WORD = re.compile(r"<(\d+):(\d+(?:\.\d+)?)>")


def fmt_time(t):
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m):02d}:{s:05.2f}"


def parse_time(text):
    """'mm:ss.xx' or plain seconds -> float seconds."""
    if ":" in text:
        m, s = text.split(":", 1)
        return int(m) * 60 + float(s)
    return float(text)


def parse_editable(text):
    """Like parse_enhanced_lrc but keeps untimed lines (time None) so they can be marked later."""
    out = []
    for raw in text.splitlines():
        if not raw.strip() or re.match(r"^\[[a-zA-Z]+:[^\]]*\]\s*$", raw):
            continue
        stamps = _TS.findall(raw)
        body = _TS.sub("", raw).strip()
        words = None
        if _WORD.search(body):
            parts = _WORD.split(body)
            words = [(int(parts[i]) * 60 + float(parts[i + 1]), parts[i + 2].strip())
                     for i in range(1, len(parts), 3) if parts[i + 2].strip()]
            body = " ".join(w for _, w in words)
        t = int(stamps[0][0]) * 60 + float(stamps[0][1]) if stamps else None
        out.append((t, body, words))
    return out


def format_lrc(lines):
    out = []
    for t, text, words in lines:
        stamp = f"[{fmt_time(t)}] " if t is not None else ""
        if words:
            text = " ".join(f"<{fmt_time(wt)}> {w}" for wt, w in words)
        out.append(f"{stamp}{text}")
    return "\n".join(out) + "\n"


def shift_lines(lines, delta_ms):
    d = delta_ms / 1000
    return [(None if t is None else max(0.0, t + d), text,
             None if not words else [(max(0.0, wt + d), w) for wt, w in words]) for t, text, words in lines]


def set_line_time(lines, index, seconds):
    out = list(lines)
    t, text, words = out[index]
    out[index] = (float(seconds), text, words)
    return out


def mark_next(lines, seconds):
    """Stamp `seconds` onto the first untimed line; returns (lines, index) or (lines, -1) if none."""
    for i, (t, text, words) in enumerate(lines):
        if t is None:
            out = list(lines)
            out[i] = (float(seconds), text, words)
            return out, i
    return list(lines), -1


def clear_times(lines):
    return [(None, text, None) for _, text, _ in lines]
