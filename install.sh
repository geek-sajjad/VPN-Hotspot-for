#!/usr/bin/env bash
# Adds VPN Hotspot to the app menu and to PATH for the current user (no sudo needed).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS="$HOME/.local/share/applications"

chmod +x "$ROOT/bin/vpn-hotspot" "$ROOT/helper/vpn-hotspot-firewall.sh"
mkdir -p "$HOME/.local/bin" "$APPS"
ln -sf "$ROOT/bin/vpn-hotspot" "$HOME/.local/bin/vpn-hotspot"

cat > "$APPS/lab.home.VpnHotspot.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=VPN Hotspot
Comment=Share this PC's VPN over a Wi-Fi hotspot
Exec=$ROOT/bin/vpn-hotspot
Icon=$ROOT/packaging/lab.home.VpnHotspot.svg
Terminal=false
Categories=Network;
Keywords=hotspot;wifi;vpn;tv;
StartupWMClass=lab.home.VpnHotspot
DESKTOP

update-desktop-database "$APPS" >/dev/null 2>&1 || true
echo "Installed. Open 'VPN Hotspot' from the app menu, or run: vpn-hotspot"
