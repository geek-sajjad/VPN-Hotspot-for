#!/usr/bin/env bash
# Removes the app-menu entry and launcher. Firewall rules are removed separately:
#   sudo helper/vpn-hotspot-firewall.sh remove <wifi-iface>
set -euo pipefail
rm -f "$HOME/.local/bin/vpn-hotspot" "$HOME/.local/share/applications/lab.home.VpnHotspot.desktop"
update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
echo "Removed. Settings are kept in ~/.config/vpn-hotspot"
