#!/usr/bin/env bash
# Installer for "MS S1 Max fans control".
# Installs the EC access module, the CLI/GUI tools, systemd units and the
# polkit rule, then enables fan control at boot.
#
# Requirements: kernel-devel for the running kernel, make/gcc. On Secure Boot
# systems the module is signed with the enrolled akmods MOK key if present.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo ./install.sh" >&2
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
KREL="$(uname -r)"

echo "==> Checking prerequisites"
[[ -d "/lib/modules/$KREL/build" ]] || {
  echo "Missing kernel headers. Install: dnf install kernel-devel-$KREL (Fedora) / linux-headers (Debian)" >&2
  exit 1
}
command -v make >/dev/null || { echo "Missing 'make' (install gcc/make)"; exit 1; }

echo "==> Installing module source to /opt/strixec"
install -d /opt/strixec
install -m 0644 "$HERE/module/strixec.c" /opt/strixec/strixec.c
install -m 0644 "$HERE/module/Makefile"  /opt/strixec/Makefile
install -m 0755 "$HERE/build-sign-load.sh" /opt/strixec/build-sign-load.sh

echo "==> Installing tools to /usr/local/bin"
install -m 0755 "$HERE/bin/strixec-setcurve" /usr/local/bin/strixec-setcurve
install -m 0755 "$HERE/bin/strixec-findfan"  /usr/local/bin/strixec-findfan
install -m 0755 "$HERE/bin/strixec-gui"      /usr/local/bin/strixec-gui

echo "==> Installing icon and desktop launcher"
install -d /usr/local/share/strixec
install -m 0644 "$HERE/share/strixec-fan.svg" /usr/local/share/strixec/strixec-fan.svg
cat > /usr/share/applications/strixec-gui.desktop <<EOF
[Desktop Entry]
Type=Application
Name=MS S1 Max fans control
Comment=Fan control for Minisforum MS-S1 MAX
Exec=/usr/local/bin/strixec-gui
Icon=/usr/local/share/strixec/strixec-fan.svg
Terminal=false
Categories=System;Settings;HardwareSettings;
EOF

echo "==> Installing systemd units and polkit rule"
install -m 0644 "$HERE/systemd/strixec.service"       /etc/systemd/system/strixec.service
install -m 0644 "$HERE/systemd/strixec-curve.service" /etc/systemd/system/strixec-curve.service
install -d /etc/polkit-1/rules.d
install -m 0644 "$HERE/polkit/49-strixec.rules" /etc/polkit-1/rules.d/49-strixec.rules

echo "==> Enabling services"
systemctl daemon-reload
systemctl enable --now strixec.service
systemctl enable --now strixec-curve.service

echo
echo "Done. Active profile:"
/usr/local/bin/strixec-setcurve show || true
echo
echo "Change profile:  sudo strixec-setcurve <ultrasilenzioso|silenzioso|leggero|bilanciato|aggressivo|stock>"
echo "GUI:             strixec-gui  (or 'MS S1 Max fans control' in the app menu)"
echo "To make a profile the boot default, edit ExecStart in /etc/systemd/system/strixec-curve.service"
