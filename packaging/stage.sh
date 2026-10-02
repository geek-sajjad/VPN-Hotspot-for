#!/usr/bin/env bash
# Copies the app into a /usr-style tree under $1. Used by build-deb.sh and build-appimage.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$1"
LIB="$DEST/usr/lib/vpn-hotspot"

install -d "$LIB/bin" "$LIB/helper" "$DEST/usr/bin" \
  "$DEST/usr/share/applications" "$DEST/usr/share/icons/hicolor/scalable/apps"
install -m 755 "$ROOT/bin/vpn-hotspot" "$LIB/bin/"
install -m 755 "$ROOT/helper/vpn-hotspot-firewall.sh" "$LIB/helper/"
install -d "$LIB/src/vpn_hotspot"
install -m 644 "$ROOT"/src/vpn_hotspot/*.py "$LIB/src/vpn_hotspot/"
ln -sf ../lib/vpn-hotspot/bin/vpn-hotspot "$DEST/usr/bin/vpn-hotspot"
install -m 644 "$ROOT/packaging/lab.home.VpnHotspot.desktop" "$DEST/usr/share/applications/"
install -m 644 "$ROOT/packaging/lab.home.VpnHotspot.svg" "$DEST/usr/share/icons/hicolor/scalable/apps/"
