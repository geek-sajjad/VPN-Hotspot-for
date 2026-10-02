"""GTK4 / libadwaita window for VPN Hotspot."""

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from . import backend  # noqa: E402

APP_ID = "lab.home.VpnHotspot"
REFRESH_SECONDS = 3


def in_background(fn, on_done):
    """Run fn in a thread and deliver (result, error) to on_done on the GTK main loop."""
    def worker():
        try:
            result, error = fn(), None
        except Exception as exc:  # shown to the user as a toast
            result, error = None, exc

        def deliver():
            on_done(result, error)
            return False
        GLib.idle_add(deliver)
    threading.Thread(target=worker, daemon=True).start()


class StatusRow(Adw.ActionRow):
    """A row with an ok / warning / error icon on the right."""

    ICONS = {
        True: ("emblem-ok-symbolic", "success"),
        False: ("dialog-error-symbolic", "error"),
        None: ("dialog-warning-symbolic", "warning"),
    }

    def __init__(self, title):
        super().__init__(title=title)
        self.icon = Gtk.Image()
        self.add_suffix(self.icon)

    def set_state(self, ok, text):
        icon_name, css = self.ICONS[ok]
        self.icon.set_from_icon_name(icon_name)
        self.icon.set_css_classes([css])
        self.set_subtitle(text)


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="VPN Hotspot", default_width=460, default_height=760)
        self.config = backend.Config.load()
        self.status = None
        self.busy = False
        self.refreshing = False
        self.fields_loaded = False
        self.shown_devices = None

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(self.toasts)
        self.set_content(view)

        page = Adw.PreferencesPage()
        self.toasts.set_child(page)
        page.add(self._build_hero())
        page.add(self._build_status_group())
        page.add(self._build_wifi_group())
        self.devices_group = Adw.PreferencesGroup(title="Connected devices")
        self.device_rows = []
        page.add(self.devices_group)
        page.add(self._build_options_group())

        self.refresh()
        GLib.timeout_add_seconds(REFRESH_SECONDS, self.refresh)

    # ---------- layout ----------

    def _build_hero(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      halign=Gtk.Align.CENTER, margin_top=6, margin_bottom=6)
        self.hero_icon = Gtk.Image(icon_name="network-wireless-hotspot-symbolic", pixel_size=96)
        self.hero_title = Gtk.Label(label="Checking…", css_classes=["title-1"])
        self.hero_subtitle = Gtk.Label(css_classes=["dim-label"], wrap=True, justify=Gtk.Justification.CENTER)

        self.spinner = Gtk.Spinner(visible=False)
        self.button_label = Gtk.Label(label="Start")
        content = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        content.append(self.spinner)
        content.append(self.button_label)
        self.button = Gtk.Button(child=content, css_classes=["pill", "suggested-action"],
                                 halign=Gtk.Align.CENTER, width_request=220, margin_top=8, sensitive=False)
        self.button.connect("clicked", self.on_button_clicked)

        for widget in (self.hero_icon, self.hero_title, self.hero_subtitle, self.button):
            box.append(widget)
        group = Adw.PreferencesGroup()
        group.add(box)
        return group

    def _build_status_group(self):
        group = Adw.PreferencesGroup(title="Status")
        self.vpn_row = StatusRow("VPN (FlClash TUN)")
        self.route_row = StatusRow("Hotspot traffic")
        self.firewall_row = StatusRow("Firewall kill switch")
        self.firewall_button = Gtk.Button(label="Install", valign=Gtk.Align.CENTER, css_classes=["flat"])
        self.firewall_button.connect("clicked", self.on_firewall_clicked)
        self.firewall_row.add_suffix(self.firewall_button)
        for row in (self.vpn_row, self.route_row, self.firewall_row):
            group.add(row)
        return group

    def _build_wifi_group(self):
        group = Adw.PreferencesGroup(title="Wi-Fi network",
                                     description="Press ✓ after editing to save. A running hotspot restarts with the new settings.")
        self.ssid_row = Adw.EntryRow(title="Network name", show_apply_button=True)
        self.password_row = Adw.PasswordEntryRow(title="Password", show_apply_button=True)
        copy = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER,
                          tooltip_text="Copy password", css_classes=["flat"])
        copy.connect("clicked", self.on_copy_password)
        self.password_row.add_suffix(copy)
        for row in (self.ssid_row, self.password_row):
            row.connect("apply", self.on_wifi_apply)
            group.add(row)
        return group

    def _build_options_group(self):
        group = Adw.PreferencesGroup(title="Options")
        row = Adw.SwitchRow(title="Turn Wi-Fi off when stopping",
                            subtitle="Keeps the PC from joining saved Wi-Fi networks",
                            active=self.config.wifi_off_on_stop)
        row.connect("notify::active", self.on_wifi_off_toggled)
        group.add(row)
        return group

    # ---------- status refresh ----------

    def refresh(self):
        if not (self.refreshing or self.busy):
            self.refreshing = True
            in_background(lambda: backend.get_status(self.config), self._on_status)
        return True  # keep the timer running

    def _on_status(self, status, error):
        self.refreshing = False
        if error:
            self.hero_subtitle.set_label(f"Could not read status: {error}")
            return
        self.status = status
        self._update_ui()

    def _update_ui(self):
        s = self.status
        if not self.fields_loaded:
            self.ssid_row.set_text(s.ssid or backend.DEFAULT_SSID)
            self.password_row.set_text(s.password or backend.generate_password())
            self.fields_loaded = True

        if not s.interface:
            self.hero_title.set_label("No Wi-Fi adapter")
            self.hero_subtitle.set_label("This PC needs a Wi-Fi card to create a hotspot.")
            self.button.set_sensitive(False)
            return

        on = s.hotspot_active
        self.hero_icon.set_css_classes(["success"] if on else ["dim-label"])
        self.hero_title.set_label("Hotspot is on" if on else "Hotspot is off")
        if on:
            count = len(s.devices)
            self.hero_subtitle.set_label(
                f"Connect to “{s.ssid}” · {count} device{'s' if count != 1 else ''} connected")
        else:
            self.hero_subtitle.set_label("Start to share this PC's VPN over Wi-Fi")
        self.button_label.set_label("Stop" if on else "Start")
        self.button.set_css_classes(["pill", "destructive-action" if on else "suggested-action"])
        self.button.set_sensitive(not self.busy)

        if s.vpn_up:
            self.vpn_row.set_state(True, "Running")
        else:
            self.vpn_row.set_state(False, "Not running. Open FlClash and turn on TUN mode")

        if not on:
            self.route_row.set_state(None, "Checked while the hotspot is on")
        elif s.routed_via_vpn:
            self.route_row.set_state(True, "Goes through FlClash (VPN)")
        else:
            self.route_row.set_state(False, f"Not going through the VPN (via {s.route_device or 'nothing'})"
                                            ". Devices get no internet")

        if self.config.firewall_installed:
            self.firewall_row.set_state(True, "Installed. Devices can only use the VPN")
            self.firewall_button.set_label("Reinstall")
        else:
            self.firewall_row.set_state(None, "Not installed. Needed once (asks for your password)")
            self.firewall_button.set_label("Install")
        self.firewall_button.set_sensitive(not self.busy)

        self._update_devices(s.devices if on else [])

    def _update_devices(self, devices):
        key = [(d.ip, d.mac, d.state) for d in devices]
        if key == self.shown_devices:
            return
        self.shown_devices = key
        for row in self.device_rows:
            self.devices_group.remove(row)
        self.device_rows = []
        if not devices:
            row = Adw.ActionRow(title="No devices", subtitle="Devices appear here after they join the hotspot")
            self.device_rows.append(row)
        for d in devices:
            row = Adw.ActionRow(title=d.ip, subtitle=d.mac)
            row.add_prefix(Gtk.Image(icon_name="network-wireless-symbolic"))
            row.add_suffix(Gtk.Label(label=d.state.lower(), css_classes=["dim-label"]))
            self.device_rows.append(row)
        for row in self.device_rows:
            self.devices_group.add(row)

    # ---------- actions ----------

    def toast(self, message):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(str(message)), timeout=5))

    def run_action(self, fn, success_message, on_success=None):
        self.busy = True
        self.button.set_sensitive(False)
        self.firewall_button.set_sensitive(False)
        self.spinner.set_visible(True)
        self.spinner.start()

        def done(_result, error):
            self.busy = False
            self.spinner.stop()
            self.spinner.set_visible(False)
            if error:
                self.toast(error)
            else:
                self.toast(success_message)
                if on_success:
                    on_success()
            self.refresh()
        in_background(fn, done)

    def confirm(self, heading, body, action_label, callback):
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", action_label)
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", lambda _d, response: response == "ok" and callback())
        dialog.present(self)

    def wifi_fields(self):
        return self.ssid_row.get_text().strip(), self.password_row.get_text()

    def on_button_clicked(self, _button):
        if self.busy or not self.status:
            return
        if self.status.hotspot_active:
            self.run_action(lambda: backend.stop(self.config), "Hotspot stopped")
            return
        error = backend.validate_wifi(*self.wifi_fields())
        if error:
            self.toast(error)
            return
        if not self.config.firewall_installed:
            self.confirm("Set up the firewall first",
                         "This one-time step lets hotspot devices use the VPN, and blocks them "
                         "from bypassing it. It asks for your admin password.",
                         "Set up", lambda: self.install_firewall(then=self.check_vpn_then_start))
            return
        self.check_vpn_then_start()

    def check_vpn_then_start(self):
        if self.status and not self.status.vpn_up:
            self.confirm("FlClash is not running",
                         "Devices on the hotspot will have no internet until you open FlClash and "
                         "turn on TUN mode.", "Start anyway", self.do_start)
            return
        self.do_start()

    def do_start(self):
        ssid, password = self.wifi_fields()
        self.run_action(lambda: backend.start(self.config, ssid, password), f"Hotspot “{ssid}” started")

    def install_firewall(self, then=None):
        iface = self.status.interface if self.status else None
        if not iface:
            self.toast("No Wi-Fi adapter found.")
            return

        def installed():
            self.config.firewall_installed = True
            self.config.save()
            if then:
                then()
        self.run_action(lambda: backend.firewall("install", iface), "Firewall rules installed", installed)

    def on_firewall_clicked(self, _button):
        if not self.busy:
            self.install_firewall()

    def on_wifi_apply(self, _row):
        ssid, password = self.wifi_fields()
        error = backend.validate_wifi(ssid, password)
        if error:
            self.toast(error)
            return
        self.run_action(lambda: backend.apply_wifi(self.config, ssid, password), "Wi-Fi settings saved")

    def on_copy_password(self, _button):
        Gdk.Display.get_default().get_clipboard().set(self.password_row.get_text())
        self.toast("Password copied")

    def on_wifi_off_toggled(self, row, _pspec):
        self.config.wifi_off_on_stop = row.get_active()
        self.config.save()


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        window = self.props.active_window or Window(self)
        window.present()


def main():
    return App().run(None)
