#!/bin/bash

set -euo pipefail

INSTALL_USER="media"
INSTALL_HOME="/home/${INSTALL_USER}"
INSTALL_ROOT="${INSTALL_HOME}/PressStart"

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo
echo "Press Start Media Installer"
echo "==========================="
echo

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Run this installer with sudo."
    echo
    echo "Example:"
    echo "  sudo ./installer/install.sh"
    exit 1
fi

if ! id "${INSTALL_USER}" >/dev/null 2>&1; then
    echo "ERROR: Required user does not exist: ${INSTALL_USER}"
    echo "Create the Raspberry Pi OS account as 'media' before installing."
    exit 1
fi

echo "[1/8] Installing system packages..."

apt-get update

DEBIAN_FRONTEND=noninteractive apt-get install -y \
    cifs-utils \
    fonts-dejavu-core \
    python3 \
    python3-paho-mqtt \
    python3-pil \
    swayimg \
    vlc

echo "[2/8] Creating Press Start directories..."

mkdir -p \
    "${INSTALL_ROOT}/app" \
    "${INSTALL_ROOT}/assets" \
    "${INSTALL_ROOT}/bin" \
    "${INSTALL_ROOT}/config" \
    "${INSTALL_ROOT}/logs" \
    "${INSTALL_ROOT}/runtime" \
    "${INSTALL_ROOT}/scripts" \
    "${INSTALL_HOME}/.config/systemd/user" \
    "/mnt/media"

echo "[3/8] Installing application files..."

rm -rf "${INSTALL_ROOT}/app/pressstart_media"

cp -a \
    "${REPOSITORY_ROOT}/src/pressstart_media" \
    "${INSTALL_ROOT}/app/pressstart_media"

cp \
    "${REPOSITORY_ROOT}/src/main.py" \
    "${INSTALL_ROOT}/app/main.py"

if [ "$(readlink -f "${REPOSITORY_ROOT}/assets")" != "$(readlink -f "${INSTALL_ROOT}/assets")" ]; then
    cp -a \
        "${REPOSITORY_ROOT}/assets/." \
        "${INSTALL_ROOT}/assets/"
fi

echo "[4/8] Installing runtime scripts..."

cp \
    "${REPOSITORY_ROOT}/scripts/start-media.sh" \
    "${INSTALL_ROOT}/bin/start-media.sh"

if [ "$(readlink -f "${REPOSITORY_ROOT}/scripts/generate-playlist.py")" != "$(readlink -f "${INSTALL_ROOT}/scripts/generate-playlist.py")" ]; then
    cp \
        "${REPOSITORY_ROOT}/scripts/generate-playlist.py" \
        "${INSTALL_ROOT}/scripts/generate-playlist.py"
fi

chmod +x \
    "${INSTALL_ROOT}/bin/start-media.sh" \
    "${INSTALL_ROOT}/scripts/generate-playlist.py"

echo "[5/8] Installing platform configuration..."

if [ ! -f "${INSTALL_ROOT}/config/media.conf" ]; then
    cp \
        "${REPOSITORY_ROOT}/config/templates/media.conf.template" \
        "${INSTALL_ROOT}/config/media.conf"
fi

# player.conf is intentionally not created here. A new player remains
# unprovisioned until Home Assistant supplies its name and profile.

echo "[6/8] Installing systemd user service..."

cp \
    "${REPOSITORY_ROOT}/systemd/pressstart-media.service" \
    "${INSTALL_HOME}/.config/systemd/user/pressstart-media.service"

echo "[7/8] Setting ownership and permissions..."

chown -R "${INSTALL_USER}:${INSTALL_USER}" \
    "${INSTALL_ROOT}" \
    "${INSTALL_HOME}/.config/systemd"

chmod 755 \
    "${INSTALL_ROOT}" \
    "${INSTALL_ROOT}/app" \
    "${INSTALL_ROOT}/assets" \
    "${INSTALL_ROOT}/bin" \
    "${INSTALL_ROOT}/runtime" \
    "${INSTALL_ROOT}/scripts"

echo "[8/8] Enabling user service..."

loginctl enable-linger "${INSTALL_USER}"

sudo -u "${INSTALL_USER}" \
    XDG_RUNTIME_DIR="/run/user/$(id -u "${INSTALL_USER}")" \
    systemctl --user daemon-reload

sudo -u "${INSTALL_USER}" \
    XDG_RUNTIME_DIR="/run/user/$(id -u "${INSTALL_USER}")" \
    systemctl --user enable pressstart-media.service

echo
echo "Installation files are in place."
echo
echo "The service has been enabled but not started."
echo
echo "A new player will remain unprovisioned until Home Assistant"
echo "supplies its player name and profile through MQTT."
echo
echo "Remaining setup before the first clean-Pi test:"
echo "  1. Install MQTT credentials."
echo "  2. Install Storage Server credentials."
echo "  3. Configure the /mnt/media mount."
echo "  4. Start or reboot into the user session."
echo
