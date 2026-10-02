"""System side of VPN Hotspot: NetworkManager (nmcli), routing checks and the firewall helper.

Everything here runs as the normal user except the firewall helper, which is
started through pkexec and asks for the admin password.
"""

import ipaddress
import json
import os
import re
import secrets
import string
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONNECTION_NAME = "TV-Hotspot"
VPN_INTERFACE = "FlClash"
DEFAULT_SSID = "VPN-Hotspot"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER = PROJECT_ROOT / "helper" / "vpn-hotspot-firewall.sh"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "vpn-hotspot"
CONFIG_FILE = CONFIG_DIR / "config.json"


class CommandError(Exception):
    pass


def run(args, check=True, timeout=30):
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        raise CommandError(message or f"{args[0]} exited with code {proc.returncode}")
    return proc.stdout


# ---------- parsing helpers (pure, unit-tested) ----------

def split_terse(line):
    """Split one line of `nmcli -t` output; nmcli escapes ':' and '\\' with a backslash."""
    fields, current, escaped = [], [], False
    for ch in line:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
    fields.append("".join(current))
    return fields


def parse_route_device(output):
    """Return the outgoing device from `ip route get` output, or None."""
    match = re.search(r"\bdev (\S+)", output)
    return match.group(1) if match else None


def parse_neighbors(output):
    """Parse `ip neigh show dev <iface>` into devices that are actually present."""
    devices = []
    for line in output.splitlines():
        parts = line.split()
        if "lladdr" not in parts:
            continue
        state = parts[-1]
        if state in ("FAILED", "INCOMPLETE"):
            continue
        devices.append(Device(ip=parts[0], mac=parts[parts.index("lladdr") + 1], state=state))
    return devices


def probe_address(cidr):
    """An address inside the hotspot subnet (not the PC itself) to test routing with."""
    iface = ipaddress.ip_interface(cidr)
    for host in iface.network.hosts():
        if host != iface.ip and int(host) - int(iface.network.network_address) >= 50:
            return str(host)
    return None


def generate_password(length=12):
    alphabet = "".join(c for c in string.ascii_letters + string.digits if c not in "0OolI1")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def validate_wifi(ssid, password):
    """Return an error message, or None when the values are usable."""
    if not 1 <= len(ssid.encode()) <= 32:
        return "Wi-Fi name must be 1–32 characters."
    if not 8 <= len(password) <= 63:
        return "Password must be 8–63 characters."
    return None


# ---------- config ----------

@dataclass
class Config:
    interface: str = ""            # empty = first Wi-Fi adapter NetworkManager reports
    wifi_off_on_stop: bool = True  # stops the PC from joining saved networks when the hotspot is off
    firewall_installed: bool = False

    @classmethod
    def load(cls):
        try:
            data = json.loads(CONFIG_FILE.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2))
        CONFIG_FILE.chmod(0o600)


# ---------- status ----------

@dataclass
class Device:
    ip: str
    mac: str
    state: str


@dataclass
class Status:
    interface: str | None = None
    hotspot_active: bool = False
    ssid: str = ""
    password: str = ""
    address: str | None = None      # e.g. 10.42.0.1/24 while the hotspot is up
    vpn_up: bool = False
    route_device: str | None = None  # where hotspot traffic would leave the PC
    devices: list = field(default_factory=list)

    @property
    def routed_via_vpn(self):
        return self.route_device == VPN_INTERFACE


def wifi_interface(config):
    if config.interface:
        return config.interface
    for line in run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device"]).splitlines():
        device, dev_type = split_terse(line)[:2]
        if dev_type == "wifi":
            return device
    return None


def connection_exists():
    names = [split_terse(l)[0] for l in run(["nmcli", "-t", "-f", "NAME", "connection", "show"]).splitlines()]
    return CONNECTION_NAME in names


def hotspot_active():
    for line in run(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"]).splitlines():
        if split_terse(line)[0] == CONNECTION_NAME:
            return True
    return False


def connection_value(field_name):
    return run(["nmcli", "-s", "-g", field_name, "connection", "show", CONNECTION_NAME]).strip()


def ipv4_address(iface):
    out = run(["ip", "-4", "-o", "addr", "show", "dev", iface, "scope", "global"], check=False)
    match = re.search(r"inet (\S+)", out)
    return match.group(1) if match else None


def vpn_up():
    try:
        flags = int((Path("/sys/class/net") / VPN_INTERFACE / "flags").read_text(), 16)
    except (FileNotFoundError, ValueError):
        return False
    return bool(flags & 0x1)  # IFF_UP


def route_device(iface, address):
    probe = probe_address(address) if address else None
    if not probe:
        return None
    out = run(["ip", "route", "get", "1.1.1.1", "from", probe, "iif", iface], check=False)
    return parse_route_device(out)


def get_status(config):
    status = Status(interface=wifi_interface(config), vpn_up=vpn_up())
    if connection_exists():
        status.ssid = connection_value("802-11-wireless.ssid")
        status.password = connection_value("802-11-wireless-security.psk")
    if not status.interface:
        return status
    status.hotspot_active = hotspot_active()
    if status.hotspot_active:
        status.address = ipv4_address(status.interface)
        status.route_device = route_device(status.interface, status.address)
        status.devices = parse_neighbors(run(["ip", "neigh", "show", "dev", status.interface], check=False))
    return status


# ---------- actions ----------

def _wait_for_radio(iface, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for line in run(["nmcli", "-t", "-f", "DEVICE,STATE", "device"]).splitlines():
            device, state = split_terse(line)[:2]
            if device == iface and state != "unavailable":
                return
        time.sleep(0.5)
    raise CommandError(f"Wi-Fi adapter {iface} did not become available. Is Wi-Fi blocked (rfkill)?")


def save_wifi(iface, ssid, password):
    """Create the hotspot connection, or update its name/password."""
    if connection_exists():
        run(["nmcli", "connection", "modify", CONNECTION_NAME,
             "connection.interface-name", iface,
             "802-11-wireless.ssid", ssid,
             "wifi-sec.psk", password])
        return
    run(["nmcli", "connection", "add", "type", "wifi", "ifname", iface,
         "con-name", CONNECTION_NAME, "autoconnect", "no", "ssid", ssid,
         "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
         "ipv4.method", "shared", "ipv6.method", "disabled",
         "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password,
         "wifi-sec.proto", "rsn", "wifi-sec.pairwise", "ccmp", "wifi-sec.group", "ccmp"])


def apply_wifi(config, ssid, password):
    """Save new Wi-Fi settings; a running hotspot is restarted so they take effect."""
    iface = wifi_interface(config)
    if not iface:
        raise CommandError("No Wi-Fi adapter found.")
    save_wifi(iface, ssid, password)
    if hotspot_active():
        run(["nmcli", "connection", "up", CONNECTION_NAME, "ifname", iface], timeout=60)


def start(config, ssid, password):
    iface = wifi_interface(config)
    if not iface:
        raise CommandError("No Wi-Fi adapter found.")
    run(["nmcli", "radio", "wifi", "on"])
    _wait_for_radio(iface)
    save_wifi(iface, ssid, password)
    run(["nmcli", "connection", "up", CONNECTION_NAME, "ifname", iface], timeout=60)


def stop(config):
    if hotspot_active():
        run(["nmcli", "connection", "down", CONNECTION_NAME])
    if config.wifi_off_on_stop:
        run(["nmcli", "radio", "wifi", "off"])


def firewall(action, iface):
    """Install or remove the hotspot firewall rules (asks for the admin password)."""
    if os.environ.get("APPIMAGE"):
        # Root cannot read files inside the AppImage's FUSE mount, so pass the script as text.
        args = ["pkexec", "/bin/bash", "-c", HELPER.read_text(), HELPER.name, action, iface]
    else:
        args = ["pkexec", str(HELPER), action, iface]
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode in (126, 127):
        raise CommandError("Authorization was cancelled.")
    if proc.returncode != 0:
        raise CommandError((proc.stderr or proc.stdout).strip() or "Firewall helper failed.")
