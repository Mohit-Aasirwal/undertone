"""Register the ctl commands as desktop keyboard shortcuts (Cinnamon, GNOME; instructions for KDE)."""
import os
import shlex
import shutil
import subprocess
import sys

DEFAULT_BINDINGS = {
    "toggle": "<Super><Alt>l",
    "cycle-vis": "<Super><Alt>v",
    "nudge +100": "<Super><Alt>Right",
    "nudge -100": "<Super><Alt>Left",
    "lyrics mark": "<Super><Alt>m",
}
LABELS = {"toggle": "toggle lyrics", "cycle-vis": "cycle visualizer", "nudge +100": "lyrics later",
          "nudge -100": "lyrics earlier", "lyrics mark": "mark lyric line"}
PREFIX = "undertone-"


def entries(exe):
    out = []
    for cmd, binding in DEFAULT_BINDINGS.items():
        group = "ctl" if not cmd.startswith("lyrics") else ""
        full = f"{exe} {group} {cmd}".replace("  ", " ").strip()
        out.append({"key": PREFIX + cmd.split()[0] + ("-later" if "+" in cmd else "-earlier" if "-1" in cmd else ""),
                    "name": f"Undertone: {LABELS[cmd]}", "command": full, "binding": binding})
    return out


def merge_list(existing, ours):
    return list(existing) + [k for k in ours if k not in existing]


def remove_ours(existing):
    return [k for k in existing if not k.startswith(PREFIX)]


def _gs(*args):
    return subprocess.run(["gsettings", *args], capture_output=True, text=True, check=True).stdout.strip()


def _parse_list(text):
    text = text.strip()
    if text in ("@as []", "[]"):
        return []
    return [p.strip().strip("'\"") for p in text.strip("[]").split(",") if p.strip()]


def _fmt_list(items):
    return "[" + ", ".join(f"'{i}'" for i in items) + "]"


def exe_path():
    return shutil.which("undertone") or f"{sys.executable} -m undertone"


def desktop():
    return os.environ.get("XDG_CURRENT_DESKTOP", "").lower()


def install():
    de = desktop()
    ours = entries(exe_path())
    if "cinnamon" in de:
        schema, base = "org.cinnamon.desktop.keybindings", "/org/cinnamon/desktop/keybindings/custom-keybindings/"
        existing = _parse_list(_gs("get", schema, "custom-list"))
        for e in ours:
            path = f"{base}{e['key']}/"
            _gs("set", f"{schema}.custom-keybinding:{path}", "name", e["name"])
            _gs("set", f"{schema}.custom-keybinding:{path}", "command", e["command"])
            _gs("set", f"{schema}.custom-keybinding:{path}", "binding", _fmt_list([e["binding"]]))
        _gs("set", schema, "custom-list", _fmt_list(merge_list(existing, [e["key"] for e in ours])))
    elif "gnome" in de or "ubuntu" in de:
        schema = "org.gnome.settings-daemon.plugins.media-keys"
        base = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
        existing = _parse_list(_gs("get", schema, "custom-keybindings"))
        paths = []
        for e in ours:
            path = f"{base}{e['key']}/"
            paths.append(path)
            for k, v in (("name", e["name"]), ("command", e["command"]), ("binding", e["binding"])):
                _gs("set", f"{schema}.custom-keybinding:{path}", k, v)
        _gs("set", schema, "custom-keybindings", _fmt_list(merge_list(existing, paths)))
    else:
        print("Automatic setup covers Cinnamon and GNOME. Bind these yourself (KDE: System Settings > Shortcuts > Custom):")
        for e in ours:
            print(f"  {e['binding']:<20} {shlex.join(e['command'].split())}")
        return
    print(f"Installed {len(ours)} shortcuts for {de}:")
    for e in ours:
        print(f"  {e['binding']:<20} {e['name']}")


def uninstall():
    de = desktop()
    if "cinnamon" in de:
        schema = "org.cinnamon.desktop.keybindings"
        existing = _parse_list(_gs("get", schema, "custom-list"))
        _gs("set", schema, "custom-list", _fmt_list(remove_ours(existing)))
        for key in existing:
            if key.startswith(PREFIX):
                subprocess.run(["dconf", "reset", "-f", f"/org/cinnamon/desktop/keybindings/custom-keybindings/{key}/"])
    elif "gnome" in de or "ubuntu" in de:
        schema = "org.gnome.settings-daemon.plugins.media-keys"
        existing = _parse_list(_gs("get", schema, "custom-keybindings"))
        keep = [p for p in existing if PREFIX not in p]
        _gs("set", schema, "custom-keybindings", _fmt_list(keep))
        for p in existing:
            if PREFIX in p:
                subprocess.run(["dconf", "reset", "-f", p])
    print("Undertone shortcuts removed.")
