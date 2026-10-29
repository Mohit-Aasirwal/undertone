const Applet = imports.ui.applet;
const PopupMenu = imports.ui.popupMenu;
const GLib = imports.gi.GLib;
const Util = imports.misc.util;

function exe() {
    const found = GLib.find_program_in_path("undertone");
    return found ? found : GLib.get_home_dir() + "/.local/bin/undertone";
}

class UndertoneApplet extends Applet.IconApplet {
    constructor(metadata, orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);
        this.set_applet_icon_symbolic_name("audio-x-generic-symbolic");
        this.set_applet_tooltip("Undertone");
        this.menuManager = new PopupMenu.PopupMenuManager(this);
        this.menu = new Applet.AppletPopupMenu(this, orientation);
        this.menuManager.addMenu(this.menu);
        const add = (label, args) => {
            const item = new PopupMenu.PopupMenuItem(label);
            item.connect("activate", () => Util.spawnCommandLine(exe() + " " + args));
            this.menu.addMenuItem(item);
        };
        add("Show / hide lyrics", "ctl toggle");
        add("Cycle visualizer", "ctl cycle-vis");
        add("Lyrics earlier (-100 ms)", "ctl nudge -100");
        add("Lyrics later (+100 ms)", "ctl nudge +100");
        add("Mark lyric line", "lyrics mark");
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        add("Start Undertone", "");
        const stop = new PopupMenu.PopupMenuItem("Stop Undertone");
        stop.connect("activate", () => Util.spawnCommandLine("pkill -f " + exe()));
        this.menu.addMenuItem(stop);
    }

    on_applet_clicked() {
        this.menu.toggle();
    }
}

function main(metadata, orientation, panelHeight, instanceId) {
    return new UndertoneApplet(metadata, orientation, panelHeight, instanceId);
}
