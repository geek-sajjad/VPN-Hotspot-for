#!/usr/bin/env bash
# Builds dist/vpn-hotspot_<version>_all.deb
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/src/vpn_hotspot/__init__.py")"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
PKG="$BUILD/vpn-hotspot"
# github.com/<owner>/<repo> from the git remote, so the package links to wherever it is published
REPO="$(git -C "$ROOT" remote get-url origin 2>/dev/null | sed -E 's#^(git@|https://)github.com[:/]##; s#\.git$##' || true)"

"$ROOT/packaging/stage.sh" "$PKG"
install -d "$PKG/DEBIAN" "$PKG/usr/share/doc/vpn-hotspot"
install -m 644 "$ROOT/README.md" "$PKG/usr/share/doc/vpn-hotspot/"
install -m 644 "$ROOT/LICENSE" "$PKG/usr/share/doc/vpn-hotspot/copyright"

cat > "$PKG/DEBIAN/control" <<CONTROL
Package: vpn-hotspot
Version: $VERSION
Section: net
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1 (>= 1.5), network-manager, ufw, iproute2, pkexec | policykit-1
Installed-Size: $(du -sk "$PKG/usr" | cut -f1)
Maintainer: $(git -C "$ROOT" log -1 --format='%an <%ae>' 2>/dev/null || echo 'vpn-hotspot maintainers <noreply@example.com>')
${REPO:+Homepage: https://github.com/$REPO
}Description: Share your PC's VPN with a TV or other devices over a Wi-Fi hotspot
 VPN Hotspot is a small GNOME app that turns a Linux PC's Wi-Fi card into a
 hotspot whose traffic goes only through the FlClash (Clash / Mihomo) TUN VPN.
 Smart TVs, game consoles and other devices that cannot run a VPN app get the
 PC's VPN connection. A UFW kill switch blocks them if the VPN is off.
CONTROL

mkdir -p "$ROOT/dist"
OUT="$ROOT/dist/vpn-hotspot_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "$PKG" "$OUT" >/dev/null
echo "$OUT"
