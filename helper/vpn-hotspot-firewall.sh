#!/usr/bin/env bash
# Root helper for VPN Hotspot. Adds or removes the UFW rules for the hotspot.
# The GUI runs it through pkexec:  pkexec vpn-hotspot-firewall.sh install|remove|status <wifi-iface>
#
# Rules: hotspot devices may get DHCP + DNS from this PC, and their traffic may
# leave ONLY through the FlClash TUN interface. If FlClash is off they get no
# internet (kill switch) instead of bypassing the VPN.
set -euo pipefail

ACTION="${1:-}"
IFACE="${2:-}"
VPN_IFACE="FlClash"

if [ "$(id -u)" -ne 0 ]; then
  echo "must run as root (via pkexec)" >&2
  exit 1
fi
if ! [[ "$IFACE" =~ ^[A-Za-z0-9_.-]{1,15}$ ]]; then
  echo "invalid interface name: '$IFACE'" >&2
  exit 2
fi
if ! command -v ufw >/dev/null; then
  echo "ufw is not installed" >&2
  exit 3
fi

# "<ufw rule>|<comment>"
RULES=(
  "allow in on $IFACE to any port 67 proto udp|vpn-hotspot DHCP"
  "allow in on $IFACE to any port 53 proto udp|vpn-hotspot DNS"
  "allow in on $IFACE to any port 53 proto tcp|vpn-hotspot DNS"
  "route allow in on $IFACE out on $VPN_IFACE|vpn-hotspot VPN only"
)

case "$ACTION" in
  install)
    for rule in "${RULES[@]}"; do
      read -ra spec <<<"${rule%%|*}"
      ufw "${spec[@]}" comment "${rule#*|}"
    done
    ;;
  remove)
    for rule in "${RULES[@]}"; do
      read -ra spec <<<"${rule%%|*}"
      if [ "${spec[0]}" = "route" ]; then
        ufw route delete "${spec[@]:1}" || true
      else
        ufw delete "${spec[@]}" || true
      fi
    done
    ;;
  status)
    ufw status | grep -c 'vpn-hotspot' || true
    exit 0
    ;;
  *)
    echo "usage: $0 install|remove|status <wifi-iface>" >&2
    exit 2
    ;;
esac

ufw reload >/dev/null
