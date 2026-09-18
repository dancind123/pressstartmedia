#!/bin/bash

set -euo pipefail

REPOSITORY_URL="https://github.com/dancind123/pressstartmedia/archive/refs/heads/main.zip"

DOWNLOAD_FILE="/tmp/pressstartmedia-main.zip"
EXTRACT_DIRECTORY="/tmp/pressstartmedia-update"
SOURCE_DIRECTORY="${EXTRACT_DIRECTORY}/pressstartmedia-main"

INSTALL_USER="media"
INSTALL_HOME="/home/${INSTALL_USER}"
INSTALL_ROOT="${INSTALL_HOME}/PressStart"

BACKUP_DIRECTORY="${INSTALL_HOME}/PressStart-backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

echo
echo "Press Start Media GitHub Update"
echo "================================"
echo

echo "[1/10] Stopping the media player..."

systemctl --user stop pressstart-media.service

echo "[2/10] Installing required packages..."

sudo apt-get update

sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    mpv \
    unzip \
    wget \
    wtype

echo "[3/10] Downloading the latest GitHub version..."

rm -f "${DOWNLOAD_FILE}"
rm -rf "${EXTRACT_DIRECTORY}"
mkdir -p "${EXTRACT_DIRECTORY}"

wget \
    --output-document="${DOWNLOAD_FILE}" \
    "${REPOSITORY_URL}"

echo "[4/10] Extracting the update..."

unzip -q "${DOWNLOAD_FILE}" -d "${EXTRACT_DIRECTORY}"

if [ ! -d "${SOURCE_DIRECTORY}/src/pressstart_media" ]; then
    echo "ERROR: The downloaded repository does not contain the expected application."
    exit 1
fi

echo "[5/10] Backing up the current installation..."

mkdir -p "${BACKUP_DIRECTORY}"

cp -a \
    "${INSTALL_ROOT}/app" \
    "${BACKUP_DIRECTORY}/app-${TIMESTAMP}"

if [ -d "${INSTALL_HOME}/.config/labwc" ]; then
    cp -a \
        "${INSTALL_HOME}/.config/labwc" \
        "${BACKUP_DIRECTORY}/labwc-${TIMESTAMP}"
fi

if [ -d "${INSTALL_HOME}/.config/pcmanfm" ]; then
    cp -a \
        "${INSTALL_HOME}/.config/pcmanfm" \
        "${BACKUP_DIRECTORY}/pcmanfm-${TIMESTAMP}"
fi

echo "[6/10] Installing the updated application..."

rm -rf "${INSTALL_ROOT}/app/pressstart_media"

cp -a \
    "${SOURCE_DIRECTORY}/src/pressstart_media" \
    "${INSTALL_ROOT}/app/pressstart_media"

cp \
    "${SOURCE_DIRECTORY}/src/main.py" \
    "${INSTALL_ROOT}/app/main.py"

cp \
    "${SOURCE_DIRECTORY}/scripts/start-media.sh" \
    "${INSTALL_ROOT}/bin/start-media.sh"

chmod +x "${INSTALL_ROOT}/bin/start-media.sh"

echo "[7/10] Installing assets and kiosk configuration..."

mkdir -p \
    "${INSTALL_ROOT}/assets" \
    "${INSTALL_HOME}/.config/labwc" \
    "${INSTALL_HOME}/.config/pcmanfm/default"

cp -a \
    "${SOURCE_DIRECTORY}/assets/." \
    "${INSTALL_ROOT}/assets/"

install -m 644 \
    "${SOURCE_DIRECTORY}/config/templates/labwc-rc.xml" \
    "${INSTALL_HOME}/.config/labwc/rc.xml"

install -m 644 \
    "${SOURCE_DIRECTORY}/config/templates/labwc-autostart" \
    "${INSTALL_HOME}/.config/labwc/autostart"

install -m 644 \
    "${SOURCE_DIRECTORY}/config/templates/pcmanfm-desktop-items-0.conf" \
    "${INSTALL_HOME}/.config/pcmanfm/default/desktop-items-0.conf"

chown -R "${INSTALL_USER}:${INSTALL_USER}" \
    "${INSTALL_ROOT}/app" \
    "${INSTALL_ROOT}/assets" \
    "${INSTALL_ROOT}/bin/start-media.sh" \
    "${INSTALL_HOME}/.config/labwc" \
    "${INSTALL_HOME}/.config/pcmanfm"

echo "[8/10] Updating the GitHub updater..."

install -m 755 \
    "${SOURCE_DIRECTORY}/scripts/update-pressstart-from-github.sh" \
    "${INSTALL_HOME}/update-pressstart-from-github.sh"

chown "${INSTALL_USER}:${INSTALL_USER}" \
    "${INSTALL_HOME}/update-pressstart-from-github.sh"

echo "[9/10] Validating the updated Python files..."

python3 -m compileall -q "${INSTALL_ROOT}/app"

echo "[10/10] Starting the media player..."

systemctl --user start pressstart-media.service

sleep 8

echo
echo "===== INSTALLED VERSION ====="

grep -R "VERSION =" \
    "${INSTALL_ROOT}/app/pressstart_media/version.py" \
    2>/dev/null || true

echo
echo "===== PLAYER CONFIGURATION ====="

cat "${INSTALL_ROOT}/config/player.conf"

echo
echo "===== ACTIVE PLAYBACK PROCESS ====="

ps -ef | grep -E '[m]pv|[v]lc' || true

echo
echo "===== SERVICE STATUS ====="

systemctl --user status pressstart-media.service --no-pager --full

echo
echo "Update complete."
echo "Application backup: ${BACKUP_DIRECTORY}/app-${TIMESTAMP}"
echo "Desktop configuration backups, when present, use the same timestamp."