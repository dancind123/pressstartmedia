#!/bin/bash

set -euo pipefail

REPOSITORY_URL="https://github.com/dancind123/pressstartmedia/archive/refs/heads/main.zip"

DOWNLOAD_FILE="/tmp/pressstartmedia-main.zip"
EXTRACT_DIRECTORY="/tmp/pressstartmedia-update"
SOURCE_DIRECTORY="${EXTRACT_DIRECTORY}/pressstartmedia-main"

INSTALL_USER="media"
INSTALL_HOME="/home/${INSTALL_USER}"
INSTALL_ROOT="${INSTALL_HOME}/PressStart"

PLAYER_CONFIG="${INSTALL_ROOT}/config/player.conf"

BACKUP_DIRECTORY="${INSTALL_HOME}/PressStart-backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

PLAYER_PROFILE=""

if [ -f "${PLAYER_CONFIG}" ]; then
    PLAYER_PROFILE="$(
        awk -F= '
            $1 == "PLAYER_PROFILE" {
                value=$2
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
                gsub(/^"|"$/, "", value)
                print value
                exit
            }
        ' "${PLAYER_CONFIG}"
    )"
fi

IS_DOWNSTAIRS=false

if [ "${PLAYER_PROFILE}" = "downstairs_bar" ]; then
    IS_DOWNSTAIRS=true
fi

echo
echo "Press Start Media GitHub Update"
echo "================================"
echo
echo "Player profile: ${PLAYER_PROFILE:-unprovisioned}"
echo

echo "[1/10] Stopping Press Start Media services..."

systemctl --user stop pressstart-media.service || true

if systemctl --user list-unit-files \
    pressstart-downstairs-displays.service \
    --no-legend 2>/dev/null \
    | grep -q '^pressstart-downstairs-displays.service'; then
    systemctl --user stop \
        pressstart-downstairs-displays.service \
        || true
fi

echo "[2/10] Installing required packages..."

sudo apt-get update

sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    mpv \
    swayimg \
    unzip \
    wget \
    wlr-randr \
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

if [ -d "${INSTALL_HOME}/.config/systemd/user" ]; then
    cp -a \
        "${INSTALL_HOME}/.config/systemd/user" \
        "${BACKUP_DIRECTORY}/systemd-user-${TIMESTAMP}"
fi

echo "[6/10] Installing the updated application..."

rm -rf "${INSTALL_ROOT}/app/pressstart_media"

cp -a \
    "${SOURCE_DIRECTORY}/src/pressstart_media" \
    "${INSTALL_ROOT}/app/pressstart_media"

cp \
    "${SOURCE_DIRECTORY}/src/main.py" \
    "${INSTALL_ROOT}/app/main.py"

install -m 755 \
    "${SOURCE_DIRECTORY}/scripts/start-media.sh" \
    "${INSTALL_ROOT}/bin/start-media.sh"

install -m 755 \
    "${SOURCE_DIRECTORY}/scripts/generate-playlist.py" \
    "${INSTALL_ROOT}/scripts/generate-playlist.py"

install -m 755 \
    "${SOURCE_DIRECTORY}/scripts/downstairs-display-keeper.sh" \
    "${INSTALL_ROOT}/bin/downstairs-display-keeper.sh"

echo "[7/10] Installing assets and kiosk configuration..."

mkdir -p \
    "${INSTALL_ROOT}/assets" \
    "${INSTALL_HOME}/.config/labwc" \
    "${INSTALL_HOME}/.config/pcmanfm/default" \
    "${INSTALL_HOME}/.config/systemd/user"

cp -a \
    "${SOURCE_DIRECTORY}/assets/." \
    "${INSTALL_ROOT}/assets/"

if [ "${IS_DOWNSTAIRS}" = true ]; then
    echo "Installing Downstairs Bar dual-display configuration."

    install -m 644 \
        "${SOURCE_DIRECTORY}/config/templates/labwc-rc-downstairs.xml" \
        "${INSTALL_HOME}/.config/labwc/rc.xml"
else
    echo "Installing standard single-display configuration."

    install -m 644 \
        "${SOURCE_DIRECTORY}/config/templates/labwc-rc.xml" \
        "${INSTALL_HOME}/.config/labwc/rc.xml"
fi

install -m 644 \
    "${SOURCE_DIRECTORY}/config/templates/labwc-autostart" \
    "${INSTALL_HOME}/.config/labwc/autostart"

install -m 644 \
    "${SOURCE_DIRECTORY}/config/templates/pcmanfm-desktop-items-0.conf" \
    "${INSTALL_HOME}/.config/pcmanfm/default/desktop-items-0.conf"

install -m 644 \
    "${SOURCE_DIRECTORY}/systemd/pressstart-downstairs-displays.service" \
    "${INSTALL_HOME}/.config/systemd/user/pressstart-downstairs-displays.service"

chown -R "${INSTALL_USER}:${INSTALL_USER}" \
    "${INSTALL_ROOT}/app" \
    "${INSTALL_ROOT}/assets" \
    "${INSTALL_ROOT}/bin" \
    "${INSTALL_ROOT}/scripts" \
    "${INSTALL_HOME}/.config/labwc" \
    "${INSTALL_HOME}/.config/pcmanfm" \
    "${INSTALL_HOME}/.config/systemd/user"

systemctl --user daemon-reload

if [ "${IS_DOWNSTAIRS}" = true ]; then
    systemctl --user enable \
        pressstart-downstairs-displays.service
else
    systemctl --user disable \
        pressstart-downstairs-displays.service \
        >/dev/null 2>&1 || true
fi

echo "[8/10] Updating the GitHub updater..."

install -m 755 \
    "${SOURCE_DIRECTORY}/scripts/update-pressstart-from-github.sh" \
    "${INSTALL_HOME}/update-pressstart-from-github.sh"

chown "${INSTALL_USER}:${INSTALL_USER}" \
    "${INSTALL_HOME}/update-pressstart-from-github.sh"

echo "[9/10] Validating the updated Python files..."

python3 -m compileall -q "${INSTALL_ROOT}/app"

echo "[10/10] Starting Press Start Media services..."

if [ "${IS_DOWNSTAIRS}" = true ]; then
    systemctl --user start \
        pressstart-downstairs-displays.service
fi

systemctl --user start pressstart-media.service

sleep 8

echo
echo "===== INSTALLED VERSION ====="

grep -R "VERSION =" \
    "${INSTALL_ROOT}/app/pressstart_media/version.py" \
    2>/dev/null || true

echo
echo "===== PLAYER CONFIGURATION ====="

if [ -f "${PLAYER_CONFIG}" ]; then
    cat "${PLAYER_CONFIG}"
else
    echo "Player is not yet provisioned."
fi

echo
echo "===== ACTIVE PLAYBACK PROCESS ====="

ps -ef | grep -E \
    '[m]pv|[v]lc|[s]wayimg|[d]ual_image_player' \
    || true

echo
echo "===== MEDIA SERVICE STATUS ====="

systemctl --user status \
    pressstart-media.service \
    --no-pager \
    --full

if [ "${IS_DOWNSTAIRS}" = true ]; then
    echo
    echo "===== DOWNSTAIRS DISPLAY SERVICE STATUS ====="

    systemctl --user status \
        pressstart-downstairs-displays.service \
        --no-pager \
        --full
fi

echo
echo "Update complete."
echo "Application backup: ${BACKUP_DIRECTORY}/app-${TIMESTAMP}"
echo "Desktop and service configuration backups, when present, use the same timestamp."