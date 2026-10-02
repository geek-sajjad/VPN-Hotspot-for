#!/usr/bin/env bash
# Builds dist/VPN_Hotspot-<version>-x86_64.AppImage
# The AppImage uses the system's Python, GTK 4 and libadwaita (which NetworkManager
# desktops already have), so it stays small.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/src/vpn_hotspot/__init__.py")"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
APPDIR="$BUILD/AppDir"

"$ROOT/packaging/stage.sh" "$APPDIR"
cp "$ROOT/packaging/lab.home.VpnHotspot.desktop" "$ROOT/packaging/lab.home.VpnHotspot.svg" "$APPDIR/"
ln -s lab.home.VpnHotspot.svg "$APPDIR/.DirIcon"
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec /usr/bin/python3 "$HERE/usr/lib/vpn-hotspot/bin/vpn-hotspot" "$@"
APPRUN
chmod 755 "$APPDIR/AppRun"

TOOL="${APPIMAGETOOL:-$ROOT/dist/.appimagetool}"
if [ ! -x "$TOOL" ]; then
  mkdir -p "$(dirname "$TOOL")"
  curl -fsSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  # Clear the AppImage magic bytes so AppImageLauncher (if installed) does not intercept the tool
  printf '\0\0\0' | dd of="$TOOL" bs=1 seek=8 conv=notrunc status=none
  chmod +x "$TOOL"
fi

mkdir -p "$ROOT/dist"
OUT="$ROOT/dist/VPN_Hotspot-${VERSION}-x86_64.AppImage"
ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$OUT" >/dev/null 2>&1 \
  || ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$OUT"
echo "$OUT"
