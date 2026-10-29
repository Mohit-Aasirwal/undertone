// GNOME Shell 45+ extension: a top-bar menu that drives `undertone ctl`.
// Untested on the author's machine (Cinnamon); please report issues.
import GLib from 'gi://GLib';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

function exe() {
    return GLib.find_program_in_path('undertone') ?? `${GLib.get_home_dir()}/.local/bin/undertone`;
}

export default class UndertoneExtension extends Extension {
    enable() {
        this._button = new PanelMenu.Button(0.0, 'Undertone', false);
        this._button.add_child(new St.Icon({icon_name: 'audio-x-generic-symbolic', style_class: 'system-status-icon'}));
        const add = (label, args) => {
            const item = new PopupMenu.PopupMenuItem(label);
            item.connect('activate', () => GLib.spawn_command_line_async(`${exe()} ${args}`.trim()));
            this._button.menu.addMenuItem(item);
        };
        add('Show / hide lyrics', 'ctl toggle');
        add('Cycle visualizer', 'ctl cycle-vis');
        add('Lyrics earlier (-100 ms)', 'ctl nudge -100');
        add('Lyrics later (+100 ms)', 'ctl nudge +100');
        add('Mark lyric line', 'lyrics mark');
        this._button.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        add('Start Undertone', '');
        Main.panel.addToStatusArea('undertone', this._button);
    }

    disable() {
        this._button?.destroy();
        this._button = null;
    }
}
