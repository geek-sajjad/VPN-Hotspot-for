"""Opens the app with demo data and saves the window as a PNG (no real network changes).

Usage, from the project root:
    python3 docs/make-screenshot.py docs/screenshot.png light
    python3 docs/make-screenshot.py docs/screenshot-dark.png dark
"""
import sys
sys.path.insert(0, "src")
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Graphene, Gtk
from vpn_hotspot import app, backend

demo = backend.Status(interface="wlp1s0", hotspot_active=True, ssid="Living-Room-TV",
                      password="k7RtxW2mPq9d", address="10.42.0.1/24", vpn_up=True,
                      route_device="FlClash",
                      devices=[backend.Device("10.42.0.57", "3c:a3:08:4f:12:9e", "REACHABLE"),
                               backend.Device("10.42.0.112", "70:2a:d5:c1:8b:04", "STALE")])
backend.get_status = lambda config: demo
backend.Config.load = classmethod(lambda cls: cls(firewall_installed=True))
backend.Config.save = lambda self: None

out = sys.argv[1]
scheme = sys.argv[2] if len(sys.argv) > 2 else "light"

def shoot(win):
    w, h = win.get_width(), win.get_height()
    snap = Gtk.Snapshot()
    Gtk.WidgetPaintable.new(win).snapshot(snap, w, h)
    tex = win.get_renderer().render_texture(snap.to_node(), Graphene.Rect().init(0, 0, w, h))
    tex.save_to_png(out)
    win.get_application().quit()
    return False

class ShotApp(app.App):
    def do_activate(self):
        Adw.StyleManager.get_default().set_color_scheme(
            Adw.ColorScheme.FORCE_DARK if scheme == "dark" else Adw.ColorScheme.FORCE_LIGHT)
        win = app.Window(self)
        win.set_default_size(460, 1075)
        win.present()
        GLib.timeout_add(1500, shoot, win)

ShotApp().run(None)
